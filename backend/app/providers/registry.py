from __future__ import annotations

from typing import Any

from app.providers.base import (
    LLMProvider,
    ProviderDescriptor,
    ProviderError,
    TTSProvider,
)


class ProviderRegistry:
    """Descriptor-based registry. No hardcoded provider names.

    Add a provider by:
      1. Implementing it in `app/providers/<name>_provider.py`
      2. Exporting `register(registry: ProviderRegistry) -> None` from that module
      3. Calling it from `build_default_registry()` in `app.providers.__init__`

    Nothing else in the codebase should know the set of provider names.
    """

    def __init__(self) -> None:
        self._descriptors: dict[str, ProviderDescriptor] = {}
        self._instances: dict[str, Any] = {}

    def register(self, descriptor: ProviderDescriptor) -> None:
        if descriptor.name in self._descriptors:
            raise ProviderError(f"Provider '{descriptor.name}' is already registered.")
        self._descriptors[descriptor.name] = descriptor

    def has(self, name: str) -> bool:
        return name in self._descriptors

    def llm(self, name: str) -> LLMProvider:
        descriptor = self._require(name)
        if not descriptor.supports_llm:
            raise ProviderError(f"Provider '{name}' does not support LLM.")
        instance = self._instance(descriptor)
        if not isinstance(instance, LLMProvider):
            raise ProviderError(
                f"Provider '{name}' is registered as LLM-capable but its factory "
                f"did not return an LLMProvider."
            )
        return instance

    def tts(self, name: str) -> TTSProvider:
        descriptor = self._require(name)
        if not descriptor.supports_tts:
            raise ProviderError(f"Provider '{name}' does not support TTS.")
        instance = self._instance(descriptor)
        if not isinstance(instance, TTSProvider):
            raise ProviderError(
                f"Provider '{name}' is registered as TTS-capable but its factory "
                f"did not return a TTSProvider."
            )
        return instance

    def langchain_model(self, name: str, temperature: float) -> Any:
        descriptor = self._require(name)
        if descriptor.langchain_factory is None:
            raise ProviderError(
                f"Provider '{name}' is not available for agent routing."
            )
        return descriptor.langchain_factory(temperature)

    def available_llm_providers(self) -> list[str]:
        return sorted(
            name
            for name, d in self._descriptors.items()
            if d.supports_llm and d.is_configured()
        )

    def available_tts_providers(self) -> list[str]:
        return sorted(
            name
            for name, d in self._descriptors.items()
            if d.supports_tts and d.is_configured()
        )

    def available_agent_providers(self) -> list[str]:
        return sorted(
            name
            for name, d in self._descriptors.items()
            if d.langchain_factory is not None and d.is_configured()
        )

    def _require(self, name: str) -> ProviderDescriptor:
        descriptor = self._descriptors.get(name)
        if descriptor is None:
            raise ProviderError(f"Unknown provider: {name}")
        return descriptor

    def _instance(self, descriptor: ProviderDescriptor) -> Any:
        cached = self._instances.get(descriptor.name)
        if cached is not None:
            return cached
        instance = descriptor.factory()
        self._instances[descriptor.name] = instance
        return instance
