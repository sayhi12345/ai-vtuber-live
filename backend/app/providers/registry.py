from __future__ import annotations

from app.providers.base import LLMProvider, ProviderError, TTSProvider
from app.providers.gemini_provider import GeminiProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.qwen_provider import QwenProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._instances: dict[str, object] = {}

    def llm(self, name: str) -> LLMProvider:
        provider = self._get(name)
        if not isinstance(provider, LLMProvider):
            raise ProviderError(f"Provider {name} does not support LLM.")
        return provider

    def tts(self, name: str) -> TTSProvider:
        provider = self._get(name)
        if not isinstance(provider, TTSProvider):
            raise ProviderError(f"Provider {name} does not support TTS.")
        return provider

    def _get(self, name: str) -> object:
        if name not in {"openai", "gemini", "qwen"}:
            raise ProviderError(f"Unsupported provider: {name}")
        if name in self._instances:
            return self._instances[name]
        if name == "openai":
            provider: object = OpenAIProvider()
        elif name == "gemini":
            provider = GeminiProvider()
        else:
            provider = QwenProvider()
        self._instances[name] = provider
        return provider
