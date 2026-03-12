from __future__ import annotations

import asyncio
import io
import logging
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.providers.base import ProviderError, TTSProvider

logger = logging.getLogger(__name__)

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
        # Fixed-size executor: pre-created threads avoid per-call OS overhead.
        # max_workers=2 limits concurrent GPU kernel dispatches to prevent OOM.
        self._executor = ThreadPoolExecutor(
            max_workers=settings.qwen_tts_max_workers,
            thread_name_prefix="qwen_tts",
        )

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        emotion: str | None = None,
    ) -> tuple[bytes, str]:
        loaded = await self._get_model()
        instruct = _EMOTION_INSTRUCTIONS.get(emotion or "neutral", settings.qwen_tts_instructions)

        loop = asyncio.get_event_loop()
        try:
            wavs, sample_rate = await loop.run_in_executor(
                self._executor,
                self._run_inference,
                loaded,
                text,
                voice or loaded.speaker,
                instruct,
            )
        except Exception as exc:  # pragma: no cover - third-party runtime errors
            raise ProviderError(f"Qwen TTS failed: {exc}") from exc

        if not wavs:
            raise ProviderError("Qwen TTS returned no audio frames.")
        return _wav_bytes(wavs[0], sample_rate), "audio/wav"

    def _run_inference(
        self,
        loaded: _LoadedModel,
        text: str,
        speaker: str,
        instruct: str,
    ) -> tuple[Any, int]:
        """Run the model synchronously inside torch.inference_mode.

        inference_mode disables both gradient tracking *and* autograd version
        counters, giving lower per-kernel dispatch overhead than no_grad alone.
        """
        import torch

        with torch.inference_mode():
            return loaded.model.generate_custom_voice(
                text=text,
                language=loaded.language,
                speaker=speaker,
                instruct=instruct,
            )

    async def _get_model(self) -> _LoadedModel:
        if self._model is not None:
            return self._model

        async with self._load_lock:
            if self._model is None:
                loop = asyncio.get_event_loop()
                self._model = await loop.run_in_executor(
                    self._executor, self._load_model
                )
        return self._model

    def _load_model(self) -> _LoadedModel:
        try:
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError as exc:
            raise ProviderError(
                "Qwen local TTS dependencies are missing. Install backend requirements first."
            ) from exc

        device = _resolve_device(torch)
        dtype = _resolve_dtype(torch, device)
        attn_implementation = _resolve_attn_implementation(device, dtype)

        logger.info(
            "Loading Qwen TTS model '%s' | device=%s | dtype=%s | attn=%s",
            settings.qwen_tts_model,
            device,
            dtype,
            attn_implementation or "default",
        )

        model_kwargs: dict[str, Any] = {"device_map": device, "dtype": dtype}
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

        if settings.qwen_tts_compile:
            logger.info("Compiling Qwen TTS model with torch.compile (mode=reduce-overhead)…")
            try:
                model = torch.compile(model, mode="reduce-overhead")
                logger.info("torch.compile complete. First inference will trigger JIT warm-up.")
            except Exception as exc:  # pragma: no cover - optional optimisation
                logger.warning("torch.compile failed, falling back to eager mode: %s", exc)

        return _LoadedModel(
            model=model,
            speaker=settings.qwen_tts_speaker,
            language=settings.qwen_tts_language,
        )


def _resolve_device(torch: Any) -> str:
    """Pick the best available compute device unless the user overrides it.

    Priority: CUDA > MPS (Apple Silicon) > CPU
    """
    configured = settings.qwen_tts_device.strip()
    if configured.lower() != "auto":
        return configured
    if torch.cuda.is_available():
        return "cuda:0"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _resolve_dtype(torch: Any, device: str) -> Any:
    """Choose the best floating-point dtype for *device*.

    - CUDA  → bfloat16 (good balance of speed and numerical stability)
    - MPS   → float16  (bfloat16 has limited MPS kernel support)
    - CPU   → float32  (half-precision is slow on CPU)
    """
    configured = settings.qwen_tts_dtype.strip().lower()
    if configured == "auto":
        if "cuda" in device:
            return torch.bfloat16
        if device == "mps":
            return torch.float16
        return torch.float32

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
    """Enable Flash Attention only on CUDA with a supported half-precision dtype."""
    if "cuda" not in str(device_map).lower():
        # Flash Attention is CUDA-only; skip for MPS / CPU
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
