"""Capability dispatch + descriptor registration for ProviderRegistry."""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.providers.base import (
    LLMProvider,
    ProviderDescriptor,
    ProviderError,
    TTSProvider,
)
from app.providers.registry import ProviderRegistry


class _StubLLM(LLMProvider):
    async def stream_reply(
        self, messages, system_prompt, temperature
    ) -> AsyncIterator[str]:
        if False:  # pragma: no cover
            yield ""


class _StubTTS(TTSProvider):
    async def synthesize(self, text, voice=None, emotion=None):
        return b"", "audio/mpeg"


def test_unknown_name_raises_provider_error():
    registry = ProviderRegistry()
    with pytest.raises(ProviderError, match="Unknown provider"):
        registry.llm("nope")


def test_capability_mismatch_llm_only_descriptor_rejects_tts_call():
    registry = ProviderRegistry()
    registry.register(
        ProviderDescriptor(
            name="llm-only",
            factory=_StubLLM,
            supports_llm=True,
            supports_tts=False,
        )
    )
    assert isinstance(registry.llm("llm-only"), LLMProvider)
    with pytest.raises(ProviderError, match="does not support TTS"):
        registry.tts("llm-only")


def test_capability_mismatch_tts_only_descriptor_rejects_llm_call():
    registry = ProviderRegistry()
    registry.register(
        ProviderDescriptor(
            name="tts-only",
            factory=_StubTTS,
            supports_llm=False,
            supports_tts=True,
        )
    )
    assert isinstance(registry.tts("tts-only"), TTSProvider)
    with pytest.raises(ProviderError, match="does not support LLM"):
        registry.llm("tts-only")


def test_missing_langchain_factory_rejects_agent_dispatch():
    registry = ProviderRegistry()
    registry.register(
        ProviderDescriptor(
            name="plain-llm",
            factory=_StubLLM,
            supports_llm=True,
        )
    )
    with pytest.raises(ProviderError, match="not available for agent routing"):
        registry.langchain_model("plain-llm", temperature=0.5)


def test_duplicate_register_raises():
    registry = ProviderRegistry()
    descriptor = ProviderDescriptor(
        name="dup", factory=_StubLLM, supports_llm=True
    )
    registry.register(descriptor)
    with pytest.raises(ProviderError, match="already registered"):
        registry.register(descriptor)


def test_factory_called_once_per_name():
    """Provider instances are cached; the factory must not be reinvoked."""
    calls = {"n": 0}

    def _factory():
        calls["n"] += 1
        return _StubLLM()

    registry = ProviderRegistry()
    registry.register(
        ProviderDescriptor(name="cached", factory=_factory, supports_llm=True)
    )
    registry.llm("cached")
    registry.llm("cached")
    registry.llm("cached")
    assert calls["n"] == 1


def test_available_lists_filter_by_is_configured():
    registry = ProviderRegistry()
    registry.register(
        ProviderDescriptor(
            name="ready",
            factory=_StubLLM,
            supports_llm=True,
            is_configured=lambda: True,
        )
    )
    registry.register(
        ProviderDescriptor(
            name="missing-key",
            factory=_StubLLM,
            supports_llm=True,
            is_configured=lambda: False,
        )
    )
    assert registry.available_llm_providers() == ["ready"]
