"""Provider factory — the single switch point between inference engines.

Call sites ask for ``get_provider(...)`` and receive something satisfying
:class:`atheria_llm.base.LLMProvider`. Changing engine is a config change.
"""

from __future__ import annotations

import structlog

from .base import LLMConfigurationError, LLMProvider
from .providers.bedrock import BedrockProvider
from .providers.gemini import GeminiProvider

logger = structlog.get_logger("atheria_llm.factory")

SUPPORTED_PROVIDERS = ("bedrock", "gemini")


def get_provider(
    *,
    provider: str,
    # Bedrock
    aws_region: str = "ap-south-1",
    bedrock_model_id: str = "apac.amazon.nova-micro-v1:0",
    guardrail_id: str | None = None,
    guardrail_version: str | None = None,
    # Gemini
    gemini_api_key: str | None = None,
    gemini_model_id: str = "gemini-2.5-flash",
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta",
) -> LLMProvider:
    """Build the configured provider.

    Raises:
        LLMConfigurationError: if the provider name is unknown or the chosen
            provider is missing required credentials.
    """
    key = (provider or "").strip().lower()

    if key == "bedrock":
        logger.info(
            "llm_provider_selected", provider=key, model_id=bedrock_model_id, region=aws_region
        )
        return BedrockProvider(
            region=aws_region,
            model_id=bedrock_model_id,
            guardrail_id=guardrail_id,
            guardrail_version=guardrail_version,
        )

    if key == "gemini":
        logger.info("llm_provider_selected", provider=key, model_id=gemini_model_id)
        return GeminiProvider(
            api_key=gemini_api_key or "",
            model_id=gemini_model_id,
            base_url=gemini_base_url,
        )

    raise LLMConfigurationError(
        f"Unknown LLM provider {provider!r}. Supported: {', '.join(SUPPORTED_PROVIDERS)}."
    )
