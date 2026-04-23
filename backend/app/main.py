from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.agents import DeepAgentRuntime, SelectiveAgentRouter
from app.characters import load_default_registry
from app.config import settings
from app.memory import (
    MemoryCuratorAgent,
    MemoryRecord,
    MemoryService,
    compose_memory_context,
)
from app.models import (
    ChatStreamRequest,
    SessionControlRequest,
    SessionMuteRequest,
    TTSRequest,
    UserCreateRequest,
    UserUpdateRequest,
)
from app.pipeline import SegmentAccumulator, detect_emotion, sse_pack, summarize_for_log
from app.providers.base import ProviderError
from app.providers.registry import ProviderRegistry
from app.safety import SafetyPipeline
from app.session_store import SessionControl, SessionEventBus, SessionStore, StageEvent, now_iso

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
providers = ProviderRegistry()
agent_router = SelectiveAgentRouter()
agent_runtime = DeepAgentRuntime()
memory_service = MemoryService(settings.mem0_api_key, settings.mem0_enabled)
memory_curator = MemoryCuratorAgent(providers)
characters = load_default_registry()
if not characters.has(settings.default_character_id):
    raise RuntimeError(
        f"DEFAULT_CHARACTER_ID '{settings.default_character_id}' is not defined in characters/definitions/."
    )


def _provider_name(requested: str | None, default_name: str) -> str:
    return (requested or default_name).lower()



@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "time": now_iso()}


@app.get("/api/characters")
async def list_characters() -> dict[str, object]:
    return {
        "default_character_id": settings.default_character_id,
        "characters": characters.list_summaries(),
    }


@app.get("/api/users")
async def list_users() -> dict[str, object]:
    return {"users": store.list_users()}


@app.post("/api/users")
async def create_user(payload: UserCreateRequest) -> dict[str, object]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="User name is required.")
    return {"user": store.create_user(name, payload.bio)}


@app.patch("/api/users/{user_id}")
async def update_user(user_id: int, payload: UserUpdateRequest) -> dict[str, object]:
    if payload.name is not None and not payload.name.strip():
        raise HTTPException(status_code=422, detail="User name is required.")
    user = store.update_user(user_id, name=payload.name, bio=payload.bio)
    if user is None:
        raise HTTPException(status_code=404, detail="Unknown user_id")
    return {"user": user}


@app.post("/api/session/reset")
async def reset_session(payload: SessionControlRequest) -> dict[str, str]:
    store.reset_session(payload.session_id)
    controls.clear_stop(payload.session_id)
    controls.set_mute(payload.session_id, False)
    return {"status": "ok", "session_id": payload.session_id}


@app.post("/api/session/stop")
async def stop_session(payload: SessionControlRequest) -> dict[str, str]:
    controls.request_stop(payload.session_id)
    await events.publish(
        payload.session_id, StageEvent(event="stopped", payload={"reason": "manual_stop"})
    )
    return {"status": "ok", "session_id": payload.session_id}


@app.post("/api/session/mute")
async def mute_session(payload: SessionMuteRequest) -> dict[str, str | bool]:
    controls.set_mute(payload.session_id, payload.muted)
    await events.publish(
        payload.session_id, StageEvent(event="mute", payload={"muted": payload.muted})
    )
    return {"status": "ok", "session_id": payload.session_id, "muted": payload.muted}


@app.get("/api/session/{session_id}/metrics")
async def session_metrics(session_id: str) -> dict[str, object]:
    return {"session_id": session_id, "metrics": store.recent_metrics(session_id)}


@app.post("/api/tts")
async def tts(payload: TTSRequest) -> Response:
    provider_name = _provider_name(payload.provider, settings.default_tts_provider)
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
        raise HTTPException(status_code=502, detail=str(exc)) from exc

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
async def stage_stream(session_id: str = Query(..., min_length=1, max_length=128)):
    queue = await events.subscribe(session_id)

    async def generator():
        try:
            yield sse_pack("ready", {"session_id": session_id})
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
    session_id = payload.session_id
    llm_provider_name = _provider_name(payload.llm_provider, settings.default_llm_provider)
    tts_provider_name = _provider_name(payload.tts_provider, settings.default_tts_provider)
    character_id = payload.character_id or settings.default_character_id
    user = store.get_user(payload.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Unknown user_id")
    if not characters.has(character_id):
        raise HTTPException(status_code=400, detail=f"Unknown character_id: {character_id}")
    character = characters.get(character_id)
    persona = character.to_system_prompt()

    async def generator():
        turn_start = time.perf_counter()
        controls.clear_stop(session_id)
        relevant_memories: list[MemoryRecord] = []

        safe_input = safety.filter_input(payload.message)
        if not safe_input.allowed:
            store.log_error(
                session_id,
                "safety_input",
                safe_input.reason or "Input blocked",
                {"original_len": len(payload.message)},
            )
            blocked_payload = {
                "message": "訊息包含高風險內容，已被系統攔截。",
                "reason": safe_input.reason,
            }
            yield sse_pack("error", blocked_payload)
            yield sse_pack("done", {"text": "", "blocked": True})
            await events.publish(session_id, StageEvent(event="error", payload=blocked_payload))
            await events.publish(session_id, StageEvent(event="done", payload={"text": ""}))
            return

        store.add_message(session_id, "user", safe_input.text, payload.user_id, character_id)

        async def _search_memories() -> list[MemoryRecord]:
            try:
                return await memory_service.search_memories(
                    query=safe_input.text,
                    user_id=payload.user_id,
                    character_id=character_id,
                    limit=settings.memory_search_limit,
                )
            except Exception as exc:
                logger.warning("Mem0 search failed: %s", exc)
                store.log_error(
                    session_id,
                    "memory_search",
                    str(exc),
                    {"user_id": payload.user_id, "character_id": character_id},
                )
                return []

        relevant_memories, history = await asyncio.gather(
            _search_memories(),
            asyncio.to_thread(
                store.get_scoped_history, payload.user_id, character_id, settings.history_limit
            ),
        )
        route = agent_router.decide(safe_input.text)
        print(f'Chat stream selected route: session_id={session_id} mode={route.mode} skills={route.skill_names} message={summarize_for_log(safe_input.text)}')
        accumulator = SegmentAccumulator()
        full_output_parts: list[str] = []
        segment_index = 0
        first_chunk_at: float | None = None

        start_payload = {
            "session_id": session_id,
            "llm_provider": llm_provider_name,
            "tts_provider": tts_provider_name,
            "mode": route.mode,
            "skills": route.skill_names,
            "timestamp": now_iso(),
        }
        yield sse_pack("start", start_payload)
        await events.publish(session_id, StageEvent(event="start", payload=start_payload))

        try:
            reply_stream: AsyncIterator[str]
            system_prompt = compose_memory_context(
                system_prompt=persona,
                user=user,
                memories=relevant_memories,
            )
            llm_messages = history
            metric_provider_name = llm_provider_name

            if route.use_agent:
                print(
                    "Chat stream dispatching request to agent runtime: session_id=%s mode=%s skills=%s llm_provider=%s",
                    session_id,
                    route.mode,
                    route.skill_names,
                    llm_provider_name,
                )
                metric_provider_name = f"agent:{llm_provider_name}"
                reply_stream = agent_runtime.stream_reply(
                    route=route,
                    provider_name=llm_provider_name,
                    messages=llm_messages,
                    system_prompt=system_prompt,
                    temperature=payload.temperature,
                )
            else:
                logger.info(
                    "Chat stream dispatching request to standard llm path: session_id=%s mode=%s llm_provider=%s",
                    session_id,
                    route.mode,
                    llm_provider_name,
                )
                llm = providers.llm(llm_provider_name)
                reply_stream = llm.stream_reply(llm_messages, system_prompt, payload.temperature)

            async for chunk in reply_stream:
                if controls.should_stop(session_id):
                    stopped_payload = {"reason": "manual_stop"}
                    yield sse_pack("stopped", stopped_payload)
                    await events.publish(
                        session_id, StageEvent(event="stopped", payload=stopped_payload)
                    )
                    break

                if first_chunk_at is None:
                    first_chunk_at = time.perf_counter()
                    ttft_ms = (first_chunk_at - turn_start) * 1000
                    store.log_metric(
                        session_id, "llm_ttft_ms", ttft_ms, metric_provider_name
                    )
                    yield sse_pack(
                        "metric",
                        {"event": "llm_ttft_ms", "value_ms": round(ttft_ms, 2)},
                    )

                safe_chunk = safety.filter_output(chunk).text
                full_output_parts.append(safe_chunk)
                yield sse_pack("delta", {"text": safe_chunk})

                for segment in accumulator.feed(safe_chunk):
                    safe_segment = safety.filter_output(segment).text
                    emotion = detect_emotion(safe_segment)
                    segment_payload = {
                        "index": segment_index,
                        "text": safe_segment,
                        "emotion": emotion,
                        "tts_provider": tts_provider_name,
                    }
                    segment_index += 1
                    yield sse_pack("segment", segment_payload)
                    await events.publish(
                        session_id, StageEvent(event="segment", payload=segment_payload)
                    )
        except ProviderError as exc:
            store.log_error(
                session_id,
                "llm",
                str(exc),
                {"provider": llm_provider_name},
            )
            error_payload = {"message": f"LLM provider error: {exc}"}
            yield sse_pack("error", error_payload)
            await events.publish(session_id, StageEvent(event="error", payload=error_payload))
            return
        except Exception as exc:  # pragma: no cover - unexpected path
            store.log_error(session_id, "chat_stream", str(exc), {})
            error_payload = {"message": "Unexpected server error."}
            yield sse_pack("error", error_payload)
            await events.publish(session_id, StageEvent(event="error", payload=error_payload))
            return

        tail = accumulator.flush()
        if tail:
            safe_tail = safety.filter_output(tail).text
            emotion = detect_emotion(safe_tail)
            segment_payload = {
                "index": segment_index,
                "text": safe_tail,
                "emotion": emotion,
                "tts_provider": tts_provider_name,
            }
            full_output_parts.append(safe_tail)
            yield sse_pack("segment", segment_payload)
            await events.publish(session_id, StageEvent(event="segment", payload=segment_payload))

        full_text = "".join(full_output_parts).strip()
        if full_text:
            store.add_message(session_id, "assistant", full_text, payload.user_id, character_id)

        total_ms = (time.perf_counter() - turn_start) * 1000
        store.log_metric(session_id, "turn_total_ms", total_ms, llm_provider_name)
        yield sse_pack("metric", {"event": "turn_total_ms", "value_ms": round(total_ms, 2)})

        done_payload = {"text": full_text, "blocked": False}
        yield sse_pack("done", done_payload)
        await events.publish(session_id, StageEvent(event="done", payload=done_payload))
        if full_text and memory_service.enabled:
            asyncio.create_task(
                _curate_and_store_memory(
                    session_id=session_id,
                    user=user,
                    character_id=character_id,
                    character_name=character.profile.name,
                    user_message=safe_input.text,
                    assistant_response=full_text,
                    existing_memories=relevant_memories,
                    provider_name=_provider_name(
                        settings.memory_curator_provider,
                        llm_provider_name,
                    ),
                )
            )

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _curate_and_store_memory(
    *,
    session_id: str,
    user: dict[str, object],
    character_id: str,
    character_name: str,
    user_message: str,
    assistant_response: str,
    existing_memories: list[MemoryRecord],
    provider_name: str,
) -> None:
    try:
        decision = await memory_curator.curate(
            user=user,
            character_id=character_id,
            character_name=character_name,
            user_message=user_message,
            assistant_response=assistant_response,
            existing_memories=existing_memories,
            provider_name=provider_name,
        )
    except Exception as exc:
        logger.warning("Memory curator failed: %s", exc)
        store.log_error(
            session_id,
            "memory_curator",
            str(exc),
            {"user_id": user.get("id"), "character_id": character_id},
        )
        return

    if not decision.should_store:
        return

    records = [
        MemoryRecord(
            content=memory.content,
            metadata={
                "character_id": character_id,
                "source": "chat",
                "category": memory.category,
                "sensitivity": memory.sensitivity,
            },
        )
        for memory in decision.memories
    ]
    try:
        await memory_service.add_memories(
            memories=records,
            user_id=int(user["id"]),
            character_id=character_id,
            run_id=session_id,
        )
    except Exception as exc:
        logger.warning("Mem0 add failed: %s", exc)
        store.log_error(
            session_id,
            "memory_add",
            str(exc),
            {"user_id": user.get("id"), "character_id": character_id},
        )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})
