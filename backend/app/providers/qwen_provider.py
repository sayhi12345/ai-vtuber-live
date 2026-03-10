from __future__ import annotations

import asyncio
import io
import wave
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.providers.base import ProviderError, TTSProvider

_EMOTION_INSTRUCTIONS: dict[str, str] = {
    "happy": "用開心、元氣十足的語氣說話，語速稍快，帶一點笑意。",
    "sad": "用輕柔、低落一點的語氣說話，語速放慢。",
    "angry": "用語氣稍強、果斷直接的方式說話，但保持清晰。",
    "surprised": "用驚訝、音調略高的語氣說話，帶一點突然反應感。",
    "shy": "用害羞、輕聲細語的方式說話，語速稍慢。",
    "thinking": "用若有所思、邊想邊說的語氣，停頓自然一些。",
    "neutral": settings.qwen_tts_instructions,
}


@dataclass(slots=True)
class _LoadedModel:
    model: Any
    speaker: str
    language: str


class QwenProvider(TTSProvider):
    def __init__(self) -> None:
        self._model: _LoadedModel | None = None
        self._load_lock = asyncio.Lock()
        self._infer_lock = asyncio.Lock()

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        emotion: str | None = None,
    ) -> tuple[bytes, str]:
        loaded = await self._get_model()
        instruct = _EMOTION_INSTRUCTIONS.get(emotion or "neutral", settings.qwen_tts_instructions)

        async with self._infer_lock:
            try:
                wavs, sample_rate = await asyncio.to_thread(
                    loaded.model.generate_custom_voice,
                    text=text,
                    language=loaded.language,
                    speaker=voice or loaded.speaker,
                    instruct=instruct,
                )
            except Exception as exc:  # pragma: no cover - third-party runtime errors
                raise ProviderError(f"Qwen TTS failed: {exc}") from exc

        if not wavs:
            raise ProviderError("Qwen TTS returned no audio frames.")
        return _wav_bytes(wavs[0], sample_rate), "audio/wav"

    async def _get_model(self) -> _LoadedModel:
        if self._model is not None:
            return self._model

        async with self._load_lock:
            if self._model is None:
                self._model = await asyncio.to_thread(self._load_model)
        return self._model

    def _load_model(self) -> _LoadedModel:
        try:
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError as exc:
            raise ProviderError(
                "Qwen local TTS dependencies are missing. Install backend requirements first."
            ) from exc

        model_kwargs: dict[str, Any] = {
            "device_map": _resolve_device(torch),
            "dtype": _resolve_dtype(torch),
        }
        attn_implementation = _resolve_attn_implementation(model_kwargs["device_map"], model_kwargs["dtype"])
        if attn_implementation:
            model_kwargs["attn_implementation"] = attn_implementation

        try:
            model = Qwen3TTSModel.from_pretrained(
                settings.qwen_tts_model,
                **model_kwargs,
            )
        except Exception as exc:  # pragma: no cover - third-party runtime errors
            raise ProviderError(
                f"Unable to load Qwen TTS model '{settings.qwen_tts_model}': {exc}"
            ) from exc

        return _LoadedModel(
            model=model,
            speaker=settings.qwen_tts_speaker,
            language=settings.qwen_tts_language,
        )


def _resolve_device(torch: Any) -> str:
    configured = settings.qwen_tts_device.strip()
    if configured.lower() != "auto":
        return configured
    return "cuda:0" if torch.cuda.is_available() else "cpu"


def _resolve_dtype(torch: Any) -> Any:
    configured = settings.qwen_tts_dtype.strip().lower()
    if configured == "auto":
        return torch.bfloat16 if torch.cuda.is_available() else torch.float32

    mapping = {
        "float16": torch.float16,
        "fp16": torch.float16,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float32": torch.float32,
        "fp32": torch.float32,
    }
    if configured not in mapping:
        raise ProviderError(f"Unsupported QWEN_TTS_DTYPE: {settings.qwen_tts_dtype}")
    return mapping[configured]


def _resolve_attn_implementation(device_map: str, dtype: Any) -> str | None:
    if "cuda" not in str(device_map).lower():
        return None
    if settings.qwen_tts_attn_implementation.strip().lower() == "none":
        return None
    dtype_name = str(dtype).lower()
    if "float16" not in dtype_name and "bfloat16" not in dtype_name:
        return None
    return settings.qwen_tts_attn_implementation


def _wav_bytes(waveform: Any, sample_rate: int) -> bytes:
    try:
        import numpy as np
    except ImportError as exc:
        raise ProviderError("numpy is required to encode Qwen TTS audio output.") from exc

    pcm = np.asarray(waveform, dtype=np.float32)
    if pcm.ndim == 2 and pcm.shape[0] in {1, 2} and pcm.shape[0] < pcm.shape[1]:
        pcm = pcm.T
    pcm = np.clip(pcm, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)

    channels = 1 if pcm.ndim == 1 else pcm.shape[1]
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm.tobytes())
        return buffer.getvalue()
