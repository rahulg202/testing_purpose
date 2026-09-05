"""Google AI Studio (Gemini) provider — the planned Bedrock replacement.

Implements the same :class:`atheria_llm.base.LLMProvider` contract as the
Bedrock provider, so switching engines is ``ATHERIA_LLM_PROVIDER=gemini`` plus
``ATHERIA_GEMINI_API_KEY`` — no service, prompt, or schema changes.

Structured output uses Gemini's native JSON mode
(``responseMimeType: application/json`` + ``responseSchema``) rather than
function calling: it is the more direct equivalent of the Bedrock forced-tool
approach and returns the payload straight in the response text.

Schema note: Gemini's ``responseSchema`` accepts a restricted OpenAPI-flavoured
subset of JSON Schema. :func:`_sanitise_schema` strips the keywords it rejects
(``additionalProperties``, ``$schema``, ``title``, ...) so the *same* schema
object used for Bedrock works here unmodified.

Network note: at the time of writing, ``generativelanguage.googleapis.com`` is
blocked by the corporate firewall on the development network (TLS reset). This
provider is complete and unit-testable, but will raise a clear connectivity
error until that egress is permitted.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..base import (
    LLMConfig,
    LLMConfigurationError,
    LLMInvocationError,
    LLMInvocationRecord,
    LLMResponse,
)

logger = structlog.get_logger("atheria_llm.gemini")

# JSON Schema keywords Gemini's responseSchema rejects.
_UNSUPPORTED_KEYS = {
    "additionalProperties",
    "$schema",
    "$id",
    "definitions",
    "$defs",
    "title",
    "default",
    "examples",
    "patternProperties",
}


def _sanitise_schema(schema: Any) -> Any:
    """Recursively drop schema keywords Gemini does not accept."""
    if isinstance(schema, dict):
        return {
            key: _sanitise_schema(value)
            for key, value in schema.items()
            if key not in _UNSUPPORTED_KEYS
        }
    if isinstance(schema, list):
        return [_sanitise_schema(item) for item in schema]
    return schema


class _TransientError(Exception):
    """Internal marker so tenacity retries only transient HTTP failures."""


class GeminiProvider:
    """Google AI Studio implementation of the LLMProvider protocol."""

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str = "gemini-2.5-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError(
                "ATHERIA_GEMINI_API_KEY is required when ATHERIA_LLM_PROVIDER=gemini."
            )
        self._api_key = api_key
        self._model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _build_payload(self, prompt: str, config: LLMConfig) -> dict[str, Any]:
        generation: dict[str, Any] = {
            "temperature": config.temperature,
            "maxOutputTokens": config.max_tokens,
        }
        if config.output_schema:
            generation["responseMimeType"] = "application/json"
            generation["responseSchema"] = _sanitise_schema(config.output_schema)

        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation,
        }
        if config.system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": config.system_prompt}]}
        return payload

    @retry(
        retry=retry_if_exception_type(_TransientError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        reraise=True,
    )
    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.post(
                url,
                json=payload,
                timeout=self._timeout,
                headers={
                    "x-goog-api-key": self._api_key,
                    "content-type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            # Covers the firewall case: TLS reset / connect failure.
            raise LLMInvocationError(
                "Could not reach the Google AI Studio endpoint "
                f"({type(exc).__name__}). On restricted networks "
                "generativelanguage.googleapis.com is often blocked; verify egress."
            ) from exc

        if response.status_code in {429, 500, 502, 503, 504}:
            raise _TransientError(f"HTTP {response.status_code}: {response.text[:200]}")
        if response.status_code in {401, 403}:
            raise LLMConfigurationError(
                f"Gemini rejected the API key (HTTP {response.status_code}). "
                "Confirm the key in Google AI Studio and that the Generative "
                "Language API is enabled."
            )
        if response.status_code >= 400:
            raise LLMInvocationError(f"Gemini HTTP {response.status_code}: {response.text[:300]}")
        return response.json()  # type: ignore[no-any-return]

    def invoke(self, prompt: str, config: LLMConfig) -> LLMResponse:
        """Run one generateContent call, returning normalised output."""
        model_id = config.model_id or self._model_id
        url = f"{self._base_url}/models/{model_id}:generateContent"
        payload = self._build_payload(prompt, config)
        started = time.perf_counter()

        try:
            raw = self._post(url, payload)
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

        candidates = raw.get("candidates") or []
        text = ""
        finish_reason = None
        if candidates:
            finish_reason = candidates[0].get("finishReason")
            for part in candidates[0].get("content", {}).get("parts", []):
                if "text" in part:
                    text += part["text"]

        structured: dict[str, Any] | None = None
        if config.output_schema and text.strip():
            try:
                parsed = json.loads(text)
                structured = parsed if isinstance(parsed, dict) else {"value": parsed}
            except json.JSONDecodeError as exc:
                raise LLMInvocationError(
                    f"Gemini returned non-JSON output despite responseSchema: {text[:200]}"
                ) from exc

        usage = raw.get("usageMetadata", {})
        record = LLMInvocationRecord(
            provider=self.name,
            model_id=model_id,
            prompt_version=config.prompt_version,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            latency_ms=latency_ms,
            stop_reason=finish_reason,
            tenant_id=config.tenant_id,
            trace_id=config.trace_id,
        )

        logger.info(
            "llm_invocation_complete",
            provider=self.name,
            model_id=model_id,
            prompt_version=config.prompt_version,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            latency_ms=round(latency_ms, 2),
            stop_reason=finish_reason,
            structured=structured is not None,
            tenant_id=config.tenant_id,
        )

        return LLMResponse(text=text, structured_output=structured, record=record, raw=raw)
