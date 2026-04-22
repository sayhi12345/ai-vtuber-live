from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "ai-vtuber-live")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    debug: bool = _bool_env("DEBUG", False)

    allowed_origins: list[str] = None  # type: ignore[assignment]

    default_llm_provider: str = os.getenv("DEFAULT_LLM_PROVIDER", "openai")
    default_tts_provider: str = os.getenv("DEFAULT_TTS_PROVIDER", "qwen")

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
    openai_chat_model: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-nano")
    openai_tts_model: str = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    openai_tts_voice: str = os.getenv("OPENAI_TTS_VOICE", "nova")
    openai_tts_instructions: str = os.getenv(
        "OPENAI_TTS_INSTRUCTIONS",
        "用自然、活潑的語氣說話，像一位個性鮮明的 AI VTuber，語速適中，情感真實。",
    )

    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    gemini_base_url: str = os.getenv(
        "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"
    )
    gemini_chat_model: str = os.getenv("GEMINI_CHAT_MODEL", "gemini-3.1-flash-lite-preview")
    gemini_tts_model: str = os.getenv(
        "GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts"
    )
    gemini_tts_voice: str = os.getenv("GEMINI_TTS_VOICE", "Leda")

    qwen_tts_model: str = os.getenv(
        "QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
    )
    qwen_tts_device: str = os.getenv("QWEN_TTS_DEVICE", "auto")
    qwen_tts_dtype: str = os.getenv("QWEN_TTS_DTYPE", "auto")
    qwen_tts_attn_implementation: str = os.getenv(
        "QWEN_TTS_ATTN_IMPLEMENTATION", "sdpa"
    )
    qwen_tts_language: str = os.getenv("QWEN_TTS_LANGUAGE", "Chinese")
    qwen_tts_speaker: str = os.getenv("QWEN_TTS_SPEAKER", "Vivian")
    qwen_tts_instructions: str = os.getenv(
        "QWEN_TTS_INSTRUCTIONS",
        "用自然、活潑的語氣說話，像一位個性鮮明的 AI VTuber，語速適中，情感真實。",
    )
    # Set to true to enable torch.compile (reduce-overhead mode).
    # First inference will be slow (~30-120s warm-up), subsequent calls are faster.
    qwen_tts_compile: bool = _bool_env("QWEN_TTS_COMPILE", True)
    # Max concurrent inference threads. Raise only if VRAM > 8 GB.
    qwen_tts_max_workers: int = int(os.getenv("QWEN_TTS_MAX_WORKERS", "4"))

    sqlite_path: str = os.getenv(
        "SQLITE_PATH",
        str((Path(__file__).resolve().parents[1] / "data" / "ai_vtuber.db")),
    )
    history_limit: int = int(os.getenv("HISTORY_LIMIT", "12"))
    safety_blocklist: list[str] = None  # type: ignore[assignment]
    default_character_id: str = os.getenv("DEFAULT_CHARACTER_ID", "luna")

    def __post_init__(self) -> None:
        if self.allowed_origins is None:
            self.allowed_origins = _csv_env(
                "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            )
        if self.safety_blocklist is None:
            self.safety_blocklist = _csv_env(
                "SAFETY_BLOCKLIST", "self-harm,kill yourself,炸彈,恐怖攻擊"
            )


settings = Settings()
