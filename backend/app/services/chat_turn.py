"""Chat turn orchestration.

Owns the per-turn pipeline: input safety → memory + history → routing →
LLM stream → segmenting → persistence → metrics → memory curation.

Yielded events are typed Pydantic models. The service publishes each event
to the session bus internally so the route doesn't have to fan out twice.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from app.agents import DeepAgentRuntime, SelectiveAgentRouter
from app.characters import CharacterRegistry
from app.config import Settings
from app.memory import (
    MemoryCuratorAgent,
    MemoryRecord,
    MemoryService,
    compose_memory_context,
)
from app.models import (
    ChatStreamRequest,
    DeltaEventData,
    DoneEventData,
    ErrorPayload,
    MetricEventData,
    SegmentEventData,
    StartEventData,
    StoppedEventData,
)
from app.pipeline import SegmentAccumulator, detect_emotion, summarize_for_log
from app.providers.base import ProviderError
from app.providers.registry import ProviderRegistry
from app.safety import SafetyPipeline
from app.session_store import (
    SessionControl,
    SessionEventBus,
    SessionStore,
    StageEvent,
    now_iso,
)

logger = logging.getLogger(__name__)


def _provider_name(requested: str | None, default_name: str) -> str:
    return (requested or default_name).lower()


class ChatTurnService:
    """One method, `run`, orchestrates a single chat turn.

    Construction takes all collaborators so the service is testable in
    isolation (swap any one of them for a fake).
    """

    def __init__(
        self,
        *,
        store: SessionStore,
        safety: SafetyPipeline,
        controls: SessionControl,
        events: SessionEventBus,
        providers: ProviderRegistry,
        agent_router: SelectiveAgentRouter,
        agent_runtime: DeepAgentRuntime,
        memory_service: MemoryService,
        memory_curator: MemoryCuratorAgent,
        characters: CharacterRegistry,
        settings: Settings,
    ) -> None:
        self._store = store
        self._safety = safety
        self._controls = controls
        self._events = events
        self._providers = providers
        self._agent_router = agent_router
        self._agent_runtime = agent_runtime
        self._memory_service = memory_service
        self._memory_curator = memory_curator
        self._characters = characters
        self._settings = settings
        self._background_tasks: set[asyncio.Task[Any]] = set()

    async def run(
        self,
        *,
        payload: ChatStreamRequest,
        user: dict[str, Any],
    ) -> AsyncIterator[tuple[str, BaseModel]]:
        """Yield (event_name, typed_payload) tuples for one chat turn.

        Side effects: publishes each event to the session bus, persists user
        and assistant messages, logs metrics, and (on success) schedules a
        memory-curation task. The caller is responsible for SSE-packing the
        yielded tuples.
        """
        session_id = payload.session_id
        llm_provider_name = _provider_name(
            payload.llm_provider, self._settings.default_llm_provider
        )
        tts_provider_name = _provider_name(
            payload.tts_provider, self._settings.default_tts_provider
        )
        character_id = payload.character_id or self._settings.default_character_id
        character = self._characters.get(character_id)
        persona = character.to_system_prompt()

        async def emit(name: str, data: BaseModel) -> tuple[str, BaseModel]:
            await self._events.publish(
                session_id,
                StageEvent(event=name, payload=data.model_dump(exclude_none=True)),
            )
            return name, data

        turn_start = time.perf_counter()
        self._controls.clear_stop(session_id)
        relevant_memories: list[MemoryRecord] = []

        safe_input = self._safety.filter_input(payload.message)
        if not safe_input.allowed:
            self._store.log_error(
                session_id,
                "safety_input",
                safe_input.reason or "Input blocked",
                {"original_len": len(payload.message)},
            )
            yield await emit(
                "error",
                ErrorPayload(
                    code="safety_blocked",
                    message="訊息包含高風險內容，已被系統攔截。",
                    retryable=False,
                ),
            )
            yield await emit("done", DoneEventData(text="", blocked=True))
            return

        self._store.add_message(
            session_id, "user", safe_input.text, payload.user_id, character_id
        )

        relevant_memories, history = await asyncio.gather(
            self._search_memories(
                session_id=session_id,
                query=safe_input.text,
                user_id=payload.user_id,
                character_id=character_id,
            ),
            asyncio.to_thread(
                self._store.get_scoped_history,
                payload.user_id,
                character_id,
                self._settings.history_limit,
            ),
        )
        route = self._agent_router.decide(safe_input.text)
        logger.info(
            "Chat stream selected route: session_id=%s mode=%s skills=%s message=%s",
            session_id,
            route.mode,
            route.skill_names,
            summarize_for_log(safe_input.text),
        )
        accumulator = SegmentAccumulator()
        full_output_parts: list[str] = []
        segment_index = 0
        first_chunk_at: float | None = None

        yield await emit(
            "start",
            StartEventData(
                session_id=session_id,
                llm_provider=llm_provider_name,
                tts_provider=tts_provider_name,
                mode=route.mode,
                skills=route.skill_names,
                timestamp=now_iso(),
            ),
        )

        try:
            system_prompt = compose_memory_context(
                system_prompt=persona,
                user=user,
                memories=relevant_memories,
            )
            metric_provider_name = llm_provider_name

            if route.use_agent:
                logger.info(
                    "Chat stream dispatching request to agent runtime: session_id=%s mode=%s skills=%s llm_provider=%s",
                    session_id,
                    route.mode,
                    route.skill_names,
                    llm_provider_name,
                )
                metric_provider_name = f"agent:{llm_provider_name}"
                reply_stream = self._agent_runtime.stream_reply(
                    route=route,
                    provider_name=llm_provider_name,
                    messages=history,
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
                llm = self._providers.llm(llm_provider_name)
                reply_stream = llm.stream_reply(
                    history, system_prompt, payload.temperature
                )

            async for chunk in reply_stream:
                if self._controls.should_stop(session_id):
                    yield await emit("stopped", StoppedEventData(reason="manual_stop"))
                    break

                if first_chunk_at is None:
                    first_chunk_at = time.perf_counter()
                    ttft_ms = (first_chunk_at - turn_start) * 1000
                    self._store.log_metric(
                        session_id, "llm_ttft_ms", ttft_ms, metric_provider_name
                    )
                    # 'metric' events are SSE-only — they don't go on the
                    # session bus to keep stage subscribers focused on
                    # user-visible state changes.
                    yield "metric", MetricEventData(
                        event="llm_ttft_ms", value_ms=round(ttft_ms, 2)
                    )

                safe_chunk = self._safety.filter_output(chunk).text
                full_output_parts.append(safe_chunk)
                yield await emit("delta", DeltaEventData(text=safe_chunk))

                for segment in accumulator.feed(safe_chunk):
                    safe_segment = self._safety.filter_output(segment).text
                    emotion = detect_emotion(safe_segment)
                    yield await emit(
                        "segment",
                        SegmentEventData(
                            index=segment_index,
                            text=safe_segment,
                            emotion=emotion,
                            tts_provider=tts_provider_name,
                        ),
                    )
                    segment_index += 1
        except ProviderError as exc:
            self._store.log_error(
                session_id,
                "llm",
                str(exc),
                {"provider": llm_provider_name},
            )
            yield await emit(
                "error",
                ErrorPayload(
                    code="llm_provider_unavailable",
                    message=f"LLM provider '{llm_provider_name}' is unavailable.",
                    retryable=True,
                ),
            )
            return
        except Exception as exc:  # pragma: no cover - unexpected path
            self._store.log_error(session_id, "chat_stream", str(exc), {})
            request_id = uuid.uuid4().hex
            logger.exception(
                "Unhandled chat_stream exception (request_id=%s)", request_id
            )
            yield await emit(
                "error",
                ErrorPayload(
                    code="server_error",
                    message="Unexpected server error.",
                    request_id=request_id,
                ),
            )
            return

        tail = accumulator.flush()
        if tail:
            safe_tail = self._safety.filter_output(tail).text
            emotion = detect_emotion(safe_tail)
            full_output_parts.append(safe_tail)
            yield await emit(
                "segment",
                SegmentEventData(
                    index=segment_index,
                    text=safe_tail,
                    emotion=emotion,
                    tts_provider=tts_provider_name,
                ),
            )

        full_text = "".join(full_output_parts).strip()
        if full_text:
            self._store.add_message(
                session_id, "assistant", full_text, payload.user_id, character_id
            )

        total_ms = (time.perf_counter() - turn_start) * 1000
        self._store.log_metric(session_id, "turn_total_ms", total_ms, llm_provider_name)
        yield "metric", MetricEventData(
            event="turn_total_ms", value_ms=round(total_ms, 2)
        )
        yield await emit("done", DoneEventData(text=full_text, blocked=False))

        if full_text and self._memory_service.enabled:
            curator_provider = _provider_name(
                self._settings.memory_curator_provider, llm_provider_name
            )
            self._spawn_background(
                self._curate_and_store_memory(
                    session_id=session_id,
                    user=user,
                    character_id=character_id,
                    character_name=character.profile.name,
                    user_message=safe_input.text,
                    assistant_response=full_text,
                    existing_memories=relevant_memories,
                    provider_name=curator_provider,
                )
            )

    # --- internals -----------------------------------------------------------

    async def _search_memories(
        self,
        *,
        session_id: str,
        query: str,
        user_id: int,
        character_id: str,
    ) -> list[MemoryRecord]:
        try:
            return await self._memory_service.search_memories(
                query=query,
                user_id=user_id,
                character_id=character_id,
                limit=self._settings.memory_search_limit,
            )
        except Exception as exc:
            logger.warning("Mem0 search failed: %s", exc)
            self._store.log_error(
                session_id,
                "memory_search",
                str(exc),
                {"user_id": user_id, "character_id": character_id},
            )
            return []

    def _spawn_background(self, coro) -> None:
        """Track fire-and-forget tasks so they don't get garbage-collected
        mid-flight and so the app can await pending work on shutdown."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _curate_and_store_memory(
        self,
        *,
        session_id: str,
        user: dict[str, Any],
        character_id: str,
        character_name: str,
        user_message: str,
        assistant_response: str,
        existing_memories: list[MemoryRecord],
        provider_name: str,
    ) -> None:
        try:
            decision = await self._memory_curator.curate(
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
            self._store.log_error(
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
            await self._memory_service.add_memories(
                memories=records,
                user_id=int(user["id"]),
                character_id=character_id,
                run_id=session_id,
            )
        except Exception as exc:
            logger.warning("Mem0 add failed: %s", exc)
            self._store.log_error(
                session_id,
                "memory_add",
                str(exc),
                {"user_id": user.get("id"), "character_id": character_id},
            )
