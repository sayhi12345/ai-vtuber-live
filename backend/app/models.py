from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


Role = Literal["system", "user", "assistant"]
LLMProviderName = Literal["openai", "gemini", "llamacpp"]
TTSProviderName = Literal["openai", "gemini", "qwen", "elevenlabs"]


class ChatMessage(BaseModel):
    role: Role
    content: str = Field(min_length=1, max_length=4000)
    timestamp: str = Field(default_factory=now_iso)


class ChatStreamRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    user_id: int = Field(ge=1)
    message: str = Field(min_length=1, max_length=4000)
    llm_provider: LLMProviderName | None = None
    tts_provider: TTSProviderName | None = None
    character_id: str | None = Field(default=None, max_length=64)
    temperature: float = Field(default=0.7, ge=0.0, le=1.5)


class UserCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    bio: str = Field(default="", max_length=1200)


class UserUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    bio: str | None = Field(default=None, max_length=1200)


class TTSRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=1200)
    provider: TTSProviderName | None = None
    voice: str | None = Field(default=None, max_length=64)
    emotion: str | None = Field(default="neutral", max_length=32)


class SessionControlRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)


class SessionMuteRequest(SessionControlRequest):
    muted: bool
