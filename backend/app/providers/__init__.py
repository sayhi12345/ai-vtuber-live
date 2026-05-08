from __future__ import annotations

from app.providers.base import (
    LLMProvider,
    ProviderDescriptor,
    ProviderError,
    TTSProvider,
)
from app.providers.registry import ProviderRegistry


def build_default_registry() -> ProviderRegistry:
    """Construct a registry pre-populated with built-in providers.

    Adding a new provider: drop a `<name>_provider.py` next to this file
    that exports `register(registry)`, then add one line below.
    """
    from app.providers import (
        elevenlabs_provider,
        gemini_provider,
        llamacpp_provider,
        openai_provider,
        qwen_provider,
    )

    registry = ProviderRegistry()
    openai_provider.register(registry)
    gemini_provider.register(registry)
    llamacpp_provider.register(registry)
    elevenlabs_provider.register(registry)
    qwen_provider.register(registry)
    return registry


__all__ = [
    "LLMProvider",
    "ProviderDescriptor",
    "ProviderError",
    "ProviderRegistry",
    "TTSProvider",
    "build_default_registry",
]
