from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


API_VERSION = "1"

Role = Literal["system", "user", "assistant"]
# Provider names are validated at the route boundary against the runtime
# ProviderRegistry (so adding a provider is a single edit). The schema stays
# `str` to keep the API contract decoupled from compiled-in provider lists.
LLMProviderName = str
TTSProviderName = str

SSEEventName = Literal[
    "ready", "start", "delta", "segment", "metric",
    "stopped", "done", "error", "mute",
]
SSE_EVENT_NAMES: list[str] = [
    "ready", "start", "delta", "segment", "metric",
    "stopped", "done", "error", "mute",
]


class ChatMessage(BaseModel):
    role: Role
    content: str = Field(min_length=1, max_length=4000)
    timestamp: str = Field(default_factory=now_iso)


class ChatStreamRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    session_token: str = Field(min_length=1, max_length=128)
    user_id: int = Field(ge=1)
    message: str = Field(min_length=1, max_length=4000)
    llm_provider: LLMProviderName | None = None
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
    session_token: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=1200)
    voice: str | None = Field(default=None, max_length=64)
    emotion: str | None = Field(default="neutral", max_length=32)


class SessionControlRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    session_token: str = Field(min_length=1, max_length=128)


class SessionMuteRequest(SessionControlRequest):
    muted: bool


class SessionCreateRequest(BaseModel):
    user_id: int | None = Field(default=None, ge=1)
    character_id: str | None = Field(default=None, max_length=64)


class SessionInfo(BaseModel):
    session_id: str
    session_token: str = Field(
        description=(
            "Opaque secret returned only at mint time. The client must echo "
            "it on every session-bound request; the server does not return "
            "it again."
        ),
    )
    user_id: int | None = None
    character_id: str | None = None
    created_at: str


# --- Unified error envelope ---------------------------------------------------
# Every HTTP error response is `{"error": ErrorPayload}`. SSE `error` events
# emit the inner `ErrorPayload` directly as the event data.

class ErrorPayload(BaseModel):
    code: str = Field(description="Machine-readable error code (e.g. 'safety_blocked').")
    message: str = Field(description="Human-readable message safe to show to end users.")
    request_id: str | None = Field(default=None, description="Server-assigned id for log correlation.")
    retryable: bool = Field(default=False, description="True if the same request may succeed if retried.")


class ErrorResponse(BaseModel):
    error: ErrorPayload


# --- SSE event payloads -------------------------------------------------------
# These are the typed payloads carried by `data:` lines on the chat and stage
# event streams. Event name is on the `event:` line; payload is one of these.

class ReadyEventData(BaseModel):
    session_id: str


class StartEventData(BaseModel):
    session_id: str
    llm_provider: str
    tts_provider: str
    mode: str
    skills: list[str]
    timestamp: str


class DeltaEventData(BaseModel):
    text: str


class SegmentEventData(BaseModel):
    index: int
    text: str
    emotion: str
    tts_provider: str


class MetricEventData(BaseModel):
    event: str
    value_ms: float


class StoppedEventData(BaseModel):
    reason: str


class DoneEventData(BaseModel):
    text: str
    blocked: bool


class MuteEventData(BaseModel):
    muted: bool


# --- Capabilities -------------------------------------------------------------

class CapabilitiesResponse(BaseModel):
    api_version: str
    default_llm_provider: str
    default_tts_provider: str
    default_character_id: str
    llm_providers: list[str]
    tts_providers: list[str]
    sse_events: list[str]
