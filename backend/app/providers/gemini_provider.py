from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator

import httpx

from app.config import settings
from app.providers.base import LLMProvider, ProviderError, TTSProvider


def _map_role(role: str) -> str:
    if role == "assistant":
        return "model"
    if role == "system":
        return "user"
    return role


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
        url = (
            f"{self._base_url}/v1beta/models/{settings.gemini_chat_model}:streamGenerateContent"
            f"?alt=sse&key={self._api_key}"
        )
        body = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {"role": _map_role(msg["role"]), "parts": [{"text": msg["content"]}]}
                for msg in messages
            ],
            "generationConfig": {"temperature": temperature},
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=body) as response:
                if response.status_code >= 400:
                    raise ProviderError(
                        f"Gemini chat failed: {response.status_code} {await response.aread()!r}"
                    )
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    try:
                        event = json.loads(payload)
                        candidates = event.get("candidates", [])
                        if not candidates:
                            continue
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            text = part.get("text")
                            if text:
                                yield text
                    except json.JSONDecodeError as exc:
                        raise ProviderError(f"Invalid Gemini stream chunk: {payload}") from exc

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
