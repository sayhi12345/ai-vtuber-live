from __future__ import annotations

import random

import httpx

from app.config import settings
from app.providers.base import ProviderError, TTSProvider

# Expressive presets driving ElevenLabs voice_settings. Each entry tweaks
# stability (lower = more variation), similarity_boost (higher = closer to the
# trained voice), and style (higher = more emotional inflection).
# https://elevenlabs.io/docs/api-reference/text-to-speech
_EMOTION_VOICE_SETTINGS: dict[str, dict[str, float]] = {
    # Project-detected emotions (from app.pipeline.detect_emotion).
    "happy":      {"stability": 0.40, "similarity_boost": 0.75, "style": 0.65},
    "sad":        {"stability": 0.75, "similarity_boost": 0.75, "style": 0.20},
    "angry":      {"stability": 0.35, "similarity_boost": 0.75, "style": 0.70},
    "surprised":  {"stability": 0.30, "similarity_boost": 0.75, "style": 0.70},
    "shy":        {"stability": 0.70, "similarity_boost": 0.75, "style": 0.25},
    "thinking":   {"stability": 0.65, "similarity_boost": 0.75, "style": 0.30},
    "neutral":    {"stability": 0.55, "similarity_boost": 0.75, "style": 0.40},
    # Expressive personality presets — used when no specific emotion was
    # detected, so each utterance picks a flavor at random for variety.
    "normal":     {"stability": 0.55, "similarity_boost": 0.75, "style": 0.30},
    "sexy":       {"stability": 0.45, "similarity_boost": 0.85, "style": 0.65},
    "playful":    {"stability": 0.35, "similarity_boost": 0.75, "style": 0.70},
    "mysterious": {"stability": 0.65, "similarity_boost": 0.80, "style": 0.55},
    "calm":       {"stability": 0.80, "similarity_boost": 0.75, "style": 0.20},
    "energetic":  {"stability": 0.30, "similarity_boost": 0.70, "style": 0.80},
    "whisper":    {"stability": 0.75, "similarity_boost": 0.80, "style": 0.40},
    "dramatic":   {"stability": 0.25, "similarity_boost": 0.65, "style": 0.85},
}

# Pool the random picker draws from when no recognized emotion is supplied.
_RANDOM_EMOTION_POOL: list[str] = [
    "normal", "sexy", "playful", "mysterious",
    "calm", "energetic", "whisper", "dramatic",
]


class ElevenLabsProvider(TTSProvider):
    """ElevenLabs TTS via /v1/text-to-speech/{voice_id}.

    Returns Opus audio (browser-native, low-latency) by default. Voice and
    model are settings-driven. When the caller passes a known emotion tag we
    map it directly; when no/unknown emotion comes in we randomly pick a
    personality preset (normal, sexy, playful, ...) so each utterance has
    a different flavor.
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

    def _resolve_emotion(self, emotion: str | None) -> tuple[str, dict[str, float]]:
        # "neutral" is the API-level default when caller didn't specify, so we
        # treat it as "no opinion" and fall back to the default flavor below.
        # A genuine non-neutral tag (happy, sad, angry, ...) still drives a
        # specific preset.
        if emotion and emotion != "neutral" and emotion in _EMOTION_VOICE_SETTINGS:
            return emotion, _EMOTION_VOICE_SETTINGS[emotion]
        # Random pick from the personality pool — re-enable for variety.
        # picked = random.choice(_RANDOM_EMOTION_POOL)
        picked = "playful"
        return picked, _EMOTION_VOICE_SETTINGS[picked]

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        emotion: str | None = None,
    ) -> tuple[bytes, str]:
        voice_id = voice or settings.elevenlabs_voice_id
        resolved, voice_settings = self._resolve_emotion(emotion)
        print(f"elevenlabs synthesize: voice={voice_id} emotion={emotion or '(none)'} -> {resolved}")

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
