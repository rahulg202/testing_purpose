"""Atheria LLM — provider-agnostic inference layer.

Import from this package only. Concrete engines (Bedrock today, Google AI
Studio next) live behind :func:`get_provider` so swapping vendors is a
configuration change rather than a code change.
"""

__version__ = "0.2.0"

from .base import (
    LLMConfig,
    LLMConfigurationError,
    LLMError,
    LLMInvocationError,
    LLMInvocationRecord,
    LLMProvider,
    LLMResponse,
)
from .factory import SUPPORTED_PROVIDERS, get_provider
from .prompts import PromptRegistry, PromptTemplate
from .providers.bedrock import BedrockProvider
from .providers.gemini import GeminiProvider

__all__ = [
    "SUPPORTED_PROVIDERS",
    "BedrockProvider",
    "GeminiProvider",
    "LLMConfig",
    "LLMConfigurationError",
    "LLMError",
    "LLMInvocationError",
    "LLMInvocationRecord",
    "LLMProvider",
    "LLMResponse",
    "PromptRegistry",
    "PromptTemplate",
    "get_provider",
]
