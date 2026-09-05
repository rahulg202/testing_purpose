"""Application-level LLM wiring.

Builds the configured provider and the prompt registry once and caches them,
so services just ask for them and stay unaware of which engine is in use.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from atheria_llm import LLMProvider, PromptRegistry, get_provider

from .config import get_settings


@lru_cache
def get_llm_provider() -> LLMProvider:
    """The configured inference provider (bedrock today, gemini switchable)."""
    settings = get_settings()
    return get_provider(
        provider=settings.llm_provider,
        aws_region=settings.aws_region,
        bedrock_model_id=settings.bedrock_model_id,
        guardrail_id=settings.bedrock_guardrail_id,
        guardrail_version=settings.bedrock_guardrail_version,
        gemini_api_key=settings.gemini_api_key,
        gemini_model_id=settings.gemini_model_id,
        gemini_base_url=settings.gemini_base_url,
    )


@lru_cache
def get_prompt_registry() -> PromptRegistry:
    """Versioned prompt templates loaded from disk.

    Resolves the prompts directory relative to the repository root so it works
    regardless of the process working directory.
    """
    settings = get_settings()
    configured = Path(settings.prompts_dir)
    if not configured.is_absolute():
        repo_root = Path(__file__).resolve().parents[3]
        configured = repo_root / configured
    return PromptRegistry(configured)
