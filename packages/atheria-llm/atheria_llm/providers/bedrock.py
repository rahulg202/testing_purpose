"""Amazon Bedrock provider (Converse API).

Structured output is obtained by forcing a single-tool call: we declare one
tool whose input schema is the caller's JSON Schema and set ``toolChoice`` to
that tool, so the model must reply with schema-shaped arguments instead of
prose. This is the most reliable structured-output mechanism Converse offers
and it works uniformly across Anthropic, Amazon Nova, and OpenAI OSS models.

Operational notes discovered against the live API:

* On-demand invocation requires an **inference-profile** ID, not a bare model
  ID. ``amazon.nova-micro-v1:0`` is rejected; ``apac.amazon.nova-micro-v1:0``
  works. A clear error is raised for this case because the AWS message is
  cryptic.
* Reasoning models (e.g. gpt-oss) spend output tokens on hidden reasoning
  before emitting the tool call, so a small ``max_tokens`` yields
  ``stopReason=max_tokens`` with no tool use. We surface that as a typed error
  telling the caller to raise the budget.
"""

from __future__ import annotations

import time
from typing import Any

import boto3
import structlog
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..base import (
    LLMConfig,
    LLMConfigurationError,
    LLMInvocationError,
    LLMInvocationRecord,
    LLMResponse,
)

logger = structlog.get_logger("atheria_llm.bedrock")

_TOOL_NAME = "structured_output"


class _ThrottledError(Exception):
    """Internal marker so tenacity retries only transient Bedrock failures."""


class BedrockProvider:
    """Bedrock Converse implementation of the LLMProvider protocol."""

    name = "bedrock"

    def __init__(
        self,
        *,
        region: str,
        model_id: str,
        guardrail_id: str | None = None,
        guardrail_version: str | None = None,
        read_timeout: int = 60,
    ) -> None:
        self._model_id = model_id
        self._guardrail_id = guardrail_id
        self._guardrail_version = guardrail_version
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=BotoConfig(
                read_timeout=read_timeout,
                connect_timeout=10,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    # -- request building ---------------------------------------------------

    def _build_request(self, prompt: str, config: LLMConfig) -> dict[str, Any]:
        model_id = config.model_id or self._model_id
        request: dict[str, Any] = {
            "modelId": model_id,
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {
                "maxTokens": config.max_tokens,
                "temperature": config.temperature,
            },
        }
        if config.system_prompt:
            request["system"] = [{"text": config.system_prompt}]

        if self._guardrail_id:
            request["guardrailConfig"] = {
                "guardrailIdentifier": self._guardrail_id,
                "guardrailVersion": self._guardrail_version or "DRAFT",
                "trace": "enabled",
            }

        if config.output_schema:
            request["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": _TOOL_NAME,
                            "description": (
                                "Return the extracted fields. Populate every property "
                                "defined by the schema."
                            ),
                            "inputSchema": {"json": config.output_schema},
                        }
                    }
                ],
                "toolChoice": {"tool": {"name": _TOOL_NAME}},
            }
        return request

    # -- invocation ---------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(_ThrottledError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        reraise=True,
    )
    def _converse(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._client.converse(**request)  # type: ignore[no-any-return]
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            message = exc.response.get("Error", {}).get("Message", str(exc))
            if code in {
                "ThrottlingException",
                "ServiceUnavailableException",
                "ModelTimeoutException",
            }:
                raise _ThrottledError(message) from exc
            if code == "ValidationException" and "on-demand throughput" in message:
                raise LLMConfigurationError(
                    f"Model '{request['modelId']}' cannot be invoked on-demand with a bare "
                    "model ID. Use the inference-profile ID for your region "
                    "(e.g. 'apac.amazon.nova-micro-v1:0' in ap-south-1). "
                    f"Bedrock said: {message}"
                ) from exc
            if code in {"AccessDeniedException", "ResourceNotFoundException"}:
                raise LLMConfigurationError(
                    f"Model '{request['modelId']}' is not accessible in this account/region. "
                    f"Bedrock said: {message}"
                ) from exc
            raise LLMInvocationError(f"Bedrock {code}: {message}") from exc

    def invoke(self, prompt: str, config: LLMConfig) -> LLMResponse:
        """Run one Converse call, returning normalised text/structured output."""
        request = self._build_request(prompt, config)
        model_id = request["modelId"]
        started = time.perf_counter()

        try:
            raw = self._converse(request)
        except Exception as exc:
            logger.error(
                "llm_invocation_failed",
                provider=self.name,
                model_id=model_id,
                prompt_version=config.prompt_version,
                error=str(exc)[:300],
                error_type=type(exc).__name__,
                tenant_id=config.tenant_id,
            )
            raise

        latency_ms = (time.perf_counter() - started) * 1000
        usage = raw.get("usage", {})
        stop_reason = raw.get("stopReason", "")

        text = ""
        structured: dict[str, Any] | None = None
        for block in raw.get("output", {}).get("message", {}).get("content", []):
            if "text" in block:
                text += block["text"]
            elif "toolUse" in block:
                structured = block["toolUse"].get("input") or {}

        guardrail_action = None
        if "trace" in raw:
            guardrail_action = raw["trace"].get("guardrail", {}).get("action")

        record = LLMInvocationRecord(
            provider=self.name,
            model_id=model_id,
            prompt_version=config.prompt_version,
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
            latency_ms=latency_ms,
            stop_reason=stop_reason,
            guardrail_id=self._guardrail_id,
            guardrail_action=guardrail_action,
            tenant_id=config.tenant_id,
            trace_id=config.trace_id,
        )

        # Fail loud: a schema was requested but the model ran out of budget
        # before emitting the tool call (typical for reasoning models).
        if config.output_schema and structured is None and stop_reason == "max_tokens":
            raise LLMInvocationError(
                f"Model '{model_id}' hit the {config.max_tokens}-token output limit before "
                "producing structured output. Increase llm_max_tokens (reasoning models "
                "consume output tokens internally before answering)."
            )

        logger.info(
            "llm_invocation_complete",
            provider=self.name,
            model_id=model_id,
            prompt_version=config.prompt_version,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            latency_ms=round(latency_ms, 2),
            stop_reason=stop_reason,
            structured=structured is not None,
            tenant_id=config.tenant_id,
        )

        return LLMResponse(text=text, structured_output=structured, record=record, raw=raw)
