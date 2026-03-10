from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


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
