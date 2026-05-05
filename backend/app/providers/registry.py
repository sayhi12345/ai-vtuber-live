from __future__ import annotations

from app.config import settings
from app.providers.base import LLMProvider, ProviderError, TTSProvider
from app.providers.elevenlabs_provider import ElevenLabsProvider
from app.providers.gemini_provider import GeminiProvider
from app.providers.llamacpp_provider import LlamaCppProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.qwen_provider import QwenProvider


def _has(value: str | None) -> bool:
    return bool(value)


# Static capability map: which providers offer LLM, TTS, and how to detect
# whether they're configured. Listed here once so /api/capabilities can answer
# without instantiating heavy providers (qwen pulls torch/transformers).
_PROVIDER_CAPABILITIES = {
    "openai": {
        "llm": True,
        "tts": True,
        "configured": lambda: _has(settings.openai_api_key),
    },
    "gemini": {
        "llm": True,
        "tts": True,
        "configured": lambda: _has(settings.gemini_api_key),
    },
    "llamacpp": {
        "llm": True,
        "tts": False,
        "configured": lambda: _has(settings.llamacpp_base_url),
    },
    "elevenlabs": {
        "llm": False,
        "tts": True,
        "configured": lambda: _has(settings.elevenlabs_api_key),
    },
    "qwen": {
        "llm": False,
        "tts": True,
        "configured": lambda: True,  # local model, always "configured"
    },
}


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

    def available_llm_providers(self) -> list[str]:
        return [
            name
            for name, caps in _PROVIDER_CAPABILITIES.items()
            if caps["llm"] and caps["configured"]()
        ]

    def available_tts_providers(self) -> list[str]:
        return [
            name
            for name, caps in _PROVIDER_CAPABILITIES.items()
            if caps["tts"] and caps["configured"]()
        ]

    def _get(self, name: str) -> object:
        if name not in _PROVIDER_CAPABILITIES:
            raise ProviderError(f"Unsupported provider: {name}")
        if name in self._instances:
            return self._instances[name]
        if name == "openai":
            provider: object = OpenAIProvider()
        elif name == "gemini":
            provider = GeminiProvider()
        elif name == "llamacpp":
            provider = LlamaCppProvider()
        elif name == "elevenlabs":
            provider = ElevenLabsProvider()
        else:
            provider = QwenProvider()
        self._instances[name] = provider
        return provider
