from __future__ import annotations

import logging
import time
import uuid
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.agents import DeepAgentRuntime, SelectiveAgentRouter
from app.characters import load_default_registry
from app.config import settings
from app.memory import MemoryCuratorAgent, MemoryService
from app.models import (
    API_VERSION,
    SSE_EVENT_NAMES,
    CapabilitiesResponse,
    ChatStreamRequest,
    ErrorPayload,
    ErrorResponse,
    MuteEventData,
    ReadyEventData,
    SessionControlRequest,
    SessionCreateRequest,
    SessionInfo,
    SessionMuteRequest,
    StoppedEventData,
    TTSRequest,
    UserCreateRequest,
    UserUpdateRequest,
)
from app.pipeline import sse_pack
from app.providers import build_default_registry
from app.providers.base import ProviderError
from app.safety import SafetyPipeline
from app.services.chat_turn import ChatTurnService
from app.session_store import (
    SessionBinding,
    SessionControl,
    SessionEventBus,
    SessionRegistry,
    SessionStore,
    StageEvent,
    now_iso,
)

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = SessionStore(settings.sqlite_path)
safety = SafetyPipeline(settings.safety_blocklist)
controls = SessionControl()
events = SessionEventBus()
session_registry = SessionRegistry()
providers = build_default_registry()
agent_router = SelectiveAgentRouter()
agent_runtime = DeepAgentRuntime(providers)
memory_service = MemoryService(settings.mem0_api_key, settings.mem0_enabled)
memory_curator = MemoryCuratorAgent(providers)
characters = load_default_registry()
if not characters.has(settings.default_character_id):
    raise RuntimeError(
        f"DEFAULT_CHARACTER_ID '{settings.default_character_id}' is not defined in characters/definitions/."
    )

chat_turn_service = ChatTurnService(
    store=store,
    safety=safety,
    controls=controls,
    events=events,
    providers=providers,
    agent_router=agent_router,
    agent_runtime=agent_runtime,
    memory_service=memory_service,
    memory_curator=memory_curator,
    characters=characters,
    settings=settings,
)


def _provider_name(requested: str | None, default_name: str) -> str:
    return (requested or default_name).lower()


def _validate_provider(name: str, capability: str) -> None:
    """Reject unknown / mis-capability'd provider names at the route boundary.

    capability is "llm" or "tts". Returns 422 with a stable error code rather
    than letting a downstream ProviderError surface as 502.
    """
    if not providers.has(name):
        raise _http_error(
            422, "unsupported_provider", f"Unsupported provider: '{name}'."
        )
    available = (
        providers.available_llm_providers()
        if capability == "llm"
        else providers.available_tts_providers()
    )
    if name not in available:
        raise _http_error(
            422,
            "unsupported_provider",
            f"Provider '{name}' is not available for {capability.upper()} "
            f"(not registered for this capability or not configured).",
        )


def _http_error(
    status: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "message": message, "retryable": retryable},
    )


def _require_session(
    session_id: str,
    session_token: str | None,
    *,
    expected_user_id: int | None = None,
) -> SessionBinding:
    """Validate the session token and (optionally) the bound user_id.

    Returns the binding so callers can read the bound user_id/character_id.
    Raises HTTPException with a stable error code on any mismatch — we
    deliberately use the same code for unknown/invalid so an attacker can't
    distinguish "no such session" from "wrong token".
    """
    binding = session_registry.validate(session_id, session_token)
    if binding is None:
        raise _http_error(
            403, "session_unauthorized", "Invalid session_id or session_token."
        )
    if (
        expected_user_id is not None
        and binding.user_id is not None
        and binding.user_id != expected_user_id
    ):
        raise _http_error(
            403,
            "session_unauthorized",
            "Session is bound to a different user.",
        )
    return binding



@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "time": now_iso()}


@app.get("/api/characters")
async def list_characters() -> dict[str, object]:
    return {
        "default_character_id": settings.default_character_id,
        "characters": characters.list_summaries(),
    }


@app.get("/api/capabilities", response_model=CapabilitiesResponse)
async def capabilities() -> CapabilitiesResponse:
    """Self-describing endpoint for frontend bootstrap.

    Lists enabled providers, the default character, and the SSE event
    vocabulary so a fresh client can adapt without hardcoding.
    """
    return CapabilitiesResponse(
        api_version=API_VERSION,
        default_llm_provider=settings.default_llm_provider,
        default_tts_provider=settings.default_tts_provider,
        default_character_id=settings.default_character_id,
        llm_providers=providers.available_llm_providers(),
        tts_providers=providers.available_tts_providers(),
        sse_events=SSE_EVENT_NAMES,
    )


@app.get("/api/users")
async def list_users() -> dict[str, object]:
    return {"users": store.list_users()}


@app.post("/api/users")
async def create_user(payload: UserCreateRequest) -> dict[str, object]:
    name = payload.name.strip()
    if not name:
        raise _http_error(422, "invalid_request", "User name is required.")
    return {"user": store.create_user(name, payload.bio)}


@app.patch("/api/users/{user_id}")
async def update_user(user_id: int, payload: UserUpdateRequest) -> dict[str, object]:
    if payload.name is not None and not payload.name.strip():
        raise _http_error(422, "invalid_request", "User name is required.")
    user = store.update_user(user_id, name=payload.name, bio=payload.bio)
    if user is None:
        raise _http_error(404, "user_not_found", "Unknown user_id")
    return {"user": user}


@app.post("/api/sessions", response_model=SessionInfo, status_code=201)
async def create_session(payload: SessionCreateRequest) -> SessionInfo:
    """Mint a server-side session.

    Returns `session_id` plus a one-time `session_token`. The token is the
    only authority for subsequent /api/session/* /api/chat/stream /api/tts
    /api/stage/stream calls — losing it requires re-minting. The id is
    UUID4 hex; the token is `secrets.token_urlsafe(32)`.
    """
    if payload.user_id is not None and store.get_user(payload.user_id) is None:
        raise _http_error(404, "user_not_found", "Unknown user_id")
    character_id = payload.character_id
    if character_id is not None and not characters.has(character_id):
        raise _http_error(
            422, "character_not_found", f"Unknown character_id: {character_id}"
        )
    binding = session_registry.mint(
        user_id=payload.user_id, character_id=character_id
    )
    return SessionInfo(
        session_id=binding.session_id,
        session_token=binding.token,
        user_id=binding.user_id,
        character_id=binding.character_id,
        created_at=binding.created_at,
    )


@app.post("/api/session/reset")
async def reset_session(payload: SessionControlRequest) -> dict[str, str]:
    _require_session(payload.session_id, payload.session_token)
    store.reset_session(payload.session_id)
    controls.clear_stop(payload.session_id)
    controls.set_mute(payload.session_id, False)
    return {"status": "ok", "session_id": payload.session_id}


@app.post("/api/session/stop")
async def stop_session(payload: SessionControlRequest) -> dict[str, str]:
    _require_session(payload.session_id, payload.session_token)
    controls.request_stop(payload.session_id)
    stopped_event = StoppedEventData(reason="manual_stop")
    await events.publish(
        payload.session_id, StageEvent(event="stopped", payload=stopped_event.model_dump())
    )
    return {"status": "ok", "session_id": payload.session_id}


@app.post("/api/session/mute")
async def mute_session(payload: SessionMuteRequest) -> dict[str, str | bool]:
    _require_session(payload.session_id, payload.session_token)
    controls.set_mute(payload.session_id, payload.muted)
    mute_event = MuteEventData(muted=payload.muted)
    await events.publish(
        payload.session_id, StageEvent(event="mute", payload=mute_event.model_dump())
    )
    return {"status": "ok", "session_id": payload.session_id, "muted": payload.muted}


@app.get("/api/session/{session_id}/metrics")
async def session_metrics(
    session_id: str,
    token: str = Query(..., min_length=1, max_length=128),
) -> dict[str, object]:
    _require_session(session_id, token)
    return {"session_id": session_id, "metrics": store.recent_metrics(session_id)}


@app.post("/api/tts")
async def tts(payload: TTSRequest) -> Response:
    _require_session(payload.session_id, payload.session_token)
    # TTS provider is no longer caller-selectable. The server picks the
    # configured default and validates it boots — clients pass text only.
    provider_name = settings.default_tts_provider.lower()
    _validate_provider(provider_name, "tts")
    if controls.is_muted(payload.session_id):
        return Response(status_code=204)

    start = time.perf_counter()
    try:
        audio_bytes, mime_type = await providers.tts(provider_name).synthesize(
            text=payload.text,
            voice=payload.voice,
            emotion=payload.emotion,
        )
    except ProviderError as exc:
        store.log_error(payload.session_id, "tts", str(exc), {"provider": provider_name})
        logger.warning("TTS provider error (%s): %s", provider_name, exc)
        raise _http_error(
            502,
            "tts_provider_unavailable",
            f"TTS provider '{provider_name}' is unavailable.",
            retryable=True,
        ) from exc

    elapsed_ms = (time.perf_counter() - start) * 1000
    store.log_metric(
        payload.session_id,
        "tts_ttfa_ms",
        elapsed_ms,
        provider_name,
        {"chars": len(payload.text), "emotion": payload.emotion},
    )
    return Response(content=audio_bytes, media_type=mime_type)


@app.get("/api/stage/stream")
async def stage_stream(
    session_id: str = Query(..., min_length=1, max_length=128),
    token: str = Query(..., min_length=1, max_length=128),
):
    # SSE via EventSource can't send custom headers, so the token rides
    # on the query string. It's session-scoped (not a user credential),
    # but URL logging still applies — re-mint to rotate.
    _require_session(session_id, token)
    queue = await events.subscribe(session_id)

    async def generator():
        try:
            yield sse_pack("ready", ReadyEventData(session_id=session_id))
            while True:
                event = await queue.get()
                yield sse_pack(event.event, event.payload)
        except asyncio.CancelledError:
            raise
        finally:
            await events.unsubscribe(session_id, queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatStreamRequest):
    """Stream a chat turn as SSE.

    The route validates inputs and pre-resolves user/character; the actual
    pipeline (safety → memory → routing → LLM → segmenting → metrics →
    persistence → memory curation) lives in `ChatTurnService`.
    """
    _require_session(
        payload.session_id,
        payload.session_token,
        expected_user_id=payload.user_id,
    )
    llm_provider_name = _provider_name(payload.llm_provider, settings.default_llm_provider)
    tts_provider_name = settings.default_tts_provider.lower()
    _validate_provider(llm_provider_name, "llm")
    _validate_provider(tts_provider_name, "tts")
    character_id = payload.character_id or settings.default_character_id
    user = store.get_user(payload.user_id)
    if user is None:
        raise _http_error(404, "user_not_found", "Unknown user_id")
    if not characters.has(character_id):
        raise _http_error(
            422, "character_not_found", f"Unknown character_id: {character_id}"
        )

    async def generator():
        async for event_name, event_data in chat_turn_service.run(
            payload=payload, user=user
        ):
            yield sse_pack(event_name, event_data)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        payload = ErrorPayload(
            code=detail["code"],
            message=detail["message"],
            retryable=bool(detail.get("retryable", False)),
            request_id=detail.get("request_id"),
        )
    else:
        payload = ErrorPayload(
            code=f"http_{exc.status_code}",
            message=str(detail) if detail else "Request failed.",
            retryable=exc.status_code >= 500,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=payload).model_dump(exclude_none=True),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    payload = ErrorPayload(
        code="invalid_request",
        message="Request body failed validation.",
        retryable=False,
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": payload.model_dump(exclude_none=True),
            "errors": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    request_id = uuid.uuid4().hex
    logger.exception("Unhandled exception (request_id=%s)", request_id)
    payload = ErrorPayload(
        code="server_error",
        message="Internal server error.",
        request_id=request_id,
        retryable=False,
    )
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(error=payload).model_dump(exclude_none=True),
    )
