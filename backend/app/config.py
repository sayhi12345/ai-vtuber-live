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
    default_tts_provider: str = os.getenv("DEFAULT_TTS_PROVIDER", "openai")

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

    sqlite_path: str = os.getenv(
        "SQLITE_PATH",
        str((Path(__file__).resolve().parents[1] / "data" / "ai_vtuber.db")),
    )
    history_limit: int = int(os.getenv("HISTORY_LIMIT", "12"))
    safety_blocklist: list[str] = None  # type: ignore[assignment]
    default_persona_prompt: str = os.getenv(
        "DEFAULT_PERSONA_PROMPT",
        (
            "你是一位有鮮明角色感的 AI VTuber。回覆要自然、可口播，維持一致語氣。"
            "避免過長句，盡量 1-2 句一段。遇到不安全或違規內容要拒答並提供替代建議。"
        ),
    )

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
