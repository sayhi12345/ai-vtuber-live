from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from urllib.parse import urlparse

import httpx
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings
from app.providers.base import LLMProvider, ProviderError, TTSProvider
from app.providers.langchain_utils import build_langchain_messages, extract_text_content


def _gemini_api_endpoint(base_url: str) -> str:
    parsed = urlparse(base_url)
    return parsed.netloc or parsed.path or base_url


class GeminiProvider(LLMProvider, TTSProvider):
    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise ProviderError("GEMINI_API_KEY is required for Gemini provider.")
        self._api_key = settings.gemini_api_key
        self._base_url = settings.gemini_base_url.rstrip("/")

    async def stream_reply(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        temperature: float,
    ) -> AsyncIterator[str]:
        prompt_messages = build_langchain_messages(messages, system_prompt)
        model_kwargs: dict[str, object] = {
            "model": settings.gemini_chat_model,
            "google_api_key": self._api_key,
            "temperature": temperature,
        }
        if self._base_url != "https://generativelanguage.googleapis.com":
            model_kwargs["client_options"] = {
                "api_endpoint": _gemini_api_endpoint(self._base_url)
            }

        chat_model = ChatGoogleGenerativeAI(**model_kwargs)

        try:
            async for chunk in chat_model.astream(prompt_messages):
                text = extract_text_content(chunk.content)
                if text:
                    yield text
        except Exception as exc:
            raise ProviderError(f"Gemini chat failed: {exc}") from exc

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        emotion: str | None = None,
    ) -> tuple[bytes, str]:
        # Gemini TTS response format may vary by model version. This implementation
        # expects inline base64 audio in candidates[].content.parts[].inlineData.data.
        url = (
            f"{self._base_url}/v1beta/models/{settings.gemini_tts_model}:generateContent"
            f"?key={self._api_key}"
        )
        body = {
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice or settings.gemini_tts_voice
                        }
                    }
                },
            },
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=body)
        if response.status_code >= 400:
            raise ProviderError(
                f"Gemini TTS failed: {response.status_code} {response.text[:500]}"
            )

        payload = response.json()
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            for part in parts:
                inline = part.get("inlineData")
                if inline and inline.get("data"):
                    audio_bytes = base64.b64decode(inline["data"])
                    mime_type = inline.get("mimeType", "audio/wav")
                    return audio_bytes, mime_type
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderError("Unable to parse Gemini TTS audio payload.") from exc

        raise ProviderError("Gemini TTS returned no audio data.")
