from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any


class ProviderError(RuntimeError):
    pass


class LLMProvider(ABC):
    @abstractmethod
    async def stream_reply(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        temperature: float,
    ) -> AsyncIterator[str]:
        raise NotImplementedError


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        emotion: str | None = None,
    ) -> tuple[bytes, str]:
        raise NotImplementedError


@dataclass(frozen=True)
class ProviderDescriptor:
    """Declarative provider metadata.

    Each provider module ships a `register(registry)` that builds one of
    these and hands it to the registry. A single descriptor describes one
    provider name; the same instance can satisfy both LLM and TTS interfaces
    (e.g. OpenAI), so capability is signalled via flags rather than separate
    factories.
    """

    name: str
    factory: Callable[[], Any]
    is_configured: Callable[[], bool] = field(default=lambda: True)
    supports_llm: bool = False
    supports_tts: bool = False
    # LangChain model builder for the deep-agent runtime. Only providers
    # that can drive an agent supply this. Takes (temperature) → ChatModel.
    langchain_factory: Callable[[float], Any] | None = None
