from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

import httpx
from langchain_openai import ChatOpenAI

from app.config import settings
from app.providers.base import LLMProvider, ProviderError, TTSProvider
from app.providers.langchain_utils import build_langchain_messages, extract_text_content

# gpt-4o-mini-tts 情緒語氣映射
# 每個 emotion tag 對應一段 instructions，控制語速、音調與情感色彩
_EMOTION_INSTRUCTIONS: dict[str, str] = {
    "happy": (
        "用開心、元氣十足的語氣說話，語速稍快，聽起來像在分享好消息，充滿活力與笑意。"
    ),
    "sad": (
        "用輕柔、略帶低落的語氣說話，語速放慢，聲音溫柔，像是在分享心裡的小遺憾。"
    ),
    "angry": (
        "用語氣稍強、直接的方式說話，語速略快，語調偏向果斷，帶一點不滿但不失禮貌。"
    ),
    "surprised": (
        "用驚訝、略帶提升的音調說話，句首稍帶喘息感，像是突然聽到很意外的事情。"
    ),
    "shy": (
        "用害羞、輕聲細語的方式說話，語速稍慢，語尾稍微上揚，聽起來有點不好意思。"
    ),
    "thinking": (
        "用若有所思、緩緩道來的語氣說話，語速偏慢，偶爾帶一點猶豫或停頓感，像在邊想邊說。"
    ),
    "neutral": (
        "用自然、穩定的語氣說話，像一位個性鮮明的 AI VTuber，語速適中，情感真實。"
    ),
}


def _normalize_openai_urls(base_url: str) -> tuple[str, str]:
    parsed = urlparse(base_url)
    path = parsed.path.rstrip("/")

    if path.endswith("/v1"):
        root_path = path[: -len("/v1")]
        api_path = path
    else:
        root_path = path
        api_path = f"{path}/v1" if path else "/v1"

    http_base_url = urlunparse(parsed._replace(path=root_path or "", params="", query="", fragment=""))
    api_base_url = urlunparse(parsed._replace(path=api_path, params="", query="", fragment=""))
    return http_base_url.rstrip("/"), api_base_url.rstrip("/")


class OpenAIProvider(LLMProvider, TTSProvider):
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ProviderError("OPENAI_API_KEY is required for OpenAI provider.")
        self._api_key = settings.openai_api_key
        self._http_base_url, self._api_base_url = _normalize_openai_urls(
            settings.openai_base_url.rstrip("/")
        )
        # Persistent client with connection pooling — avoids TCP+TLS handshake
        # on every TTS/LLM request (significant savings at ~50-150ms per call).
        self._client = httpx.AsyncClient(
            timeout=60.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def stream_reply(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        temperature: float,
    ) -> AsyncIterator[str]:
        prompt_messages = build_langchain_messages(messages, system_prompt)
        chat_model = ChatOpenAI(
            model=settings.openai_chat_model,
            api_key=self._api_key,
            base_url=self._api_base_url,
            temperature=temperature,
            streaming=True,
        )

        try:
            async for chunk in chat_model.astream(prompt_messages):
                text = extract_text_content(chunk.content)
                if text:
                    yield text
        except Exception as exc:
            raise ProviderError(f"OpenAI chat failed: {exc}") from exc

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        emotion: str | None = None,
    ) -> tuple[bytes, str]:
        instructions = _EMOTION_INSTRUCTIONS.get(
            emotion or "neutral", settings.openai_tts_instructions
        )
        body = {
            "model": settings.openai_tts_model,
            "voice": voice or settings.openai_tts_voice,
            "input": text,
            # opus: smaller than mp3, lower latency, natively supported in browsers
            "response_format": "opus",
        }
        # instructions 僅 gpt-4o-mini-tts 支援，舊版 tts-1 / tts-1-hd 會忽略
        if instructions:
            body["instructions"] = instructions

        # Stream response bytes as they arrive — no need to wait for full download
        chunks: list[bytes] = []
        async with self._client.stream(
            "POST",
            f"{self._http_base_url}/v1/audio/speech",
            headers=self._headers,
            json=body,
        ) as response:
            if response.status_code >= 400:
                body_text = (await response.aread()).decode(errors="replace")[:500]
                raise ProviderError(f"OpenAI TTS failed: {response.status_code} {body_text}")
            async for chunk in response.aiter_bytes(chunk_size=4096):
                chunks.append(chunk)

        return b"".join(chunks), "audio/ogg"
