from __future__ import annotations

import httpx

from app.config import settings
from app.providers.base import ProviderError, TTSProvider

# ElevenLabs voice_settings adjustments per emotion. Defaults sit in the
# middle of the [0, 1] range so we can push either direction.
# https://elevenlabs.io/docs/api-reference/text-to-speech
_EMOTION_VOICE_SETTINGS: dict[str, dict[str, float]] = {
    "happy":      {"stability": 0.40, "similarity_boost": 0.75, "style": 0.65},
    "sad":        {"stability": 0.75, "similarity_boost": 0.75, "style": 0.20},
    "angry":      {"stability": 0.35, "similarity_boost": 0.75, "style": 0.70},
    "surprised":  {"stability": 0.30, "similarity_boost": 0.75, "style": 0.70},
    "shy":        {"stability": 0.70, "similarity_boost": 0.75, "style": 0.25},
    "thinking":   {"stability": 0.65, "similarity_boost": 0.75, "style": 0.30},
    "neutral":    {"stability": 0.55, "similarity_boost": 0.75, "style": 0.40},
}


class ElevenLabsProvider(TTSProvider):
    """ElevenLabs TTS via /v1/text-to-speech/{voice_id}.

    Returns Opus audio (browser-native, low-latency) by default. Voice and
    model are settings-driven; emotion tags map to voice_settings tweaks.
    """

    def __init__(self) -> None:
        if not settings.elevenlabs_api_key:
            raise ProviderError("ELEVENLABS_API_KEY is required for ElevenLabs provider.")
        self._api_key = settings.elevenlabs_api_key
        self._base_url = settings.elevenlabs_base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=60.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        emotion: str | None = None,
    ) -> tuple[bytes, str]:
        voice_id = voice or settings.elevenlabs_voice_id
        voice_settings = _EMOTION_VOICE_SETTINGS.get(
            emotion or "neutral", _EMOTION_VOICE_SETTINGS["neutral"]
        )

        body = {
            "text": text,
            "model_id": settings.elevenlabs_model,
            "voice_settings": {**voice_settings, "use_speaker_boost": True},
        }
        # opus_48000_64 is the smallest browser-native opus tier — fine for chat
        params = {"output_format": "opus_48000_64"}
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/ogg",
        }

        chunks: list[bytes] = []
        async with self._client.stream(
            "POST",
            f"{self._base_url}/v1/text-to-speech/{voice_id}/stream",
            headers=headers,
            params=params,
            json=body,
        ) as response:
            if response.status_code >= 400:
                body_text = (await response.aread()).decode(errors="replace")[:500]
                raise ProviderError(
                    f"ElevenLabs TTS failed: {response.status_code} {body_text}"
                )
            async for chunk in response.aiter_bytes(chunk_size=4096):
                chunks.append(chunk)

        return b"".join(chunks), "audio/ogg"
