"""Provider-agnostic LLM interface.

Atheria must not be welded to one inference vendor. Every call site depends on
this module only: :class:`LLMConfig` in, :class:`LLMResponse` out. Swapping
Amazon Bedrock for Google AI Studio (or anything else) means adding a provider
class and flipping ``ATHERIA_LLM_PROVIDER`` — no service or prompt changes.

Two invariants matter for regulatory defensibility and are enforced here
rather than left to each provider:

1. Every invocation returns an :class:`LLMInvocationRecord` naming the exact
   ``model_id`` and ``prompt_version`` that produced the output, so the audit
   trail can answer "which model/prompt said this?".
2. Structured output is requested via a JSON schema and returned parsed. A
   provider that cannot honour the schema must raise, never silently degrade
   to free text — that is the "fail loud, never silent" principle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class LLMError(RuntimeError):
    """Base class for provider failures.

    Raised (rather than swallowed) so callers can mark a pipeline stage as a
    terminal error with a typed reason instead of proceeding on bad data.
    """


class LLMConfigurationError(LLMError):
    """The provider is not usable as configured (missing key, bad model id)."""


class LLMInvocationError(LLMError):
    """The provider was reachable but the call failed or returned nothing usable."""


class LLMInvocationRecord(BaseModel):
    """Audit record for a single inference call.

    Persisted alongside any value the model produced so an inspector can trace
    every AI-derived field back to the precise model and prompt version.
    """

    provider: str
    model_id: str
    prompt_version: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    stop_reason: str | None = None
    guardrail_id: str | None = None
    guardrail_action: str | None = None
    tenant_id: str | None = None
    trace_id: str | None = None
    error: str | None = None


@dataclass
class LLMConfig:
    """Everything a provider needs for one call.

    ``model_id`` is intentionally optional: each provider substitutes its own
    configured default so call sites stay provider-agnostic.
    """

    prompt_version: str = "unversioned"
    system_prompt: str | None = None
    model_id: str | None = None
    max_tokens: int = 2000
    temperature: float = 0.0
    #: JSON Schema. When set, the provider MUST return matching parsed JSON.
    output_schema: dict[str, Any] | None = None
    tenant_id: str | None = None
    trace_id: str | None = None


@dataclass
class LLMResponse:
    """Normalised result of an inference call."""

    text: str = ""
    structured_output: dict[str, Any] | None = None
    record: LLMInvocationRecord | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def require_structured(self) -> dict[str, Any]:
        """Return the structured payload or fail loudly.

        Used by extraction/triage paths where free text is not an acceptable
        substitute for schema-conformant output.
        """
        if not self.structured_output:
            raise LLMInvocationError(
                "Model returned no structured output despite a schema being requested "
                f"(stop_reason={self.record.stop_reason if self.record else 'unknown'})"
            )
        return self.structured_output


@runtime_checkable
class LLMProvider(Protocol):
    """The contract every inference backend implements."""

    #: Short stable name recorded in audit events, e.g. "bedrock", "gemini".
    name: str

    def invoke(self, prompt: str, config: LLMConfig) -> LLMResponse:
        """Run one completion and return a normalised response."""
        ...
