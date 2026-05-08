"""Smoke + branch tests for ChatTurnService.

The refactor's whole reason to exist is to make this orchestration testable
in isolation, so every collaborator is a fake. We only assert on the SSE
event sequence, the persistence side effects, and the error envelope shape
— not on the wording of human-readable messages.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.routing import AgentRouteDecision, SelectiveAgentRouter
from app.memory import MemoryRecord
from app.models import ChatStreamRequest, ErrorPayload
from app.providers.base import LLMProvider, ProviderError
from app.safety import SafetyResult
from app.services.chat_turn import ChatTurnService


# --- Fakes ------------------------------------------------------------------


class FakeStore:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str, int, str]] = []
        self.metrics: list[tuple[str, str, float, str]] = []
        self.errors: list[tuple[str, str, str]] = []
        self.history: list[dict[str, str]] = []

    def add_message(self, session_id, role, content, user_id, character_id):
        self.messages.append((session_id, role, content, user_id, character_id))

    def get_scoped_history(self, user_id, character_id, limit):
        return list(self.history)

    def log_metric(self, session_id, event, value_ms, provider, meta=None):
        self.metrics.append((session_id, event, value_ms, provider))

    def log_error(self, session_id, stage, message, meta=None):
        self.errors.append((session_id, stage, message))


class FakeSafety:
    """Allows everything; passes text through unchanged."""

    def filter_input(self, text: str) -> SafetyResult:
        return SafetyResult(allowed=True, text=text)

    def filter_output(self, text: str) -> SafetyResult:
        return SafetyResult(allowed=True, text=text)


class BlockingSafety(FakeSafety):
    def filter_input(self, text: str) -> SafetyResult:
        return SafetyResult(allowed=False, text="", reason="blocked-by-test")


class FakeControls:
    def __init__(self, *, stop_after: int | None = None) -> None:
        self._stop_after = stop_after
        self._chunks_seen = 0
        self._stopped = False
        self.cleared: list[str] = []

    def clear_stop(self, session_id: str) -> None:
        self.cleared.append(session_id)
        self._stopped = False
        self._chunks_seen = 0

    def should_stop(self, session_id: str) -> bool:
        if self._stop_after is None:
            return False
        if self._chunks_seen >= self._stop_after:
            return True
        self._chunks_seen += 1
        return False


class FakeBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []  # (session_id, event_name)

    async def publish(self, session_id: str, event) -> None:
        self.published.append((session_id, event.event))


class FakeLLM(LLMProvider):
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    async def stream_reply(self, messages, system_prompt, temperature):
        for chunk in self._chunks:
            await asyncio.sleep(0)
            yield chunk


class FailingLLM(LLMProvider):
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def stream_reply(self, messages, system_prompt, temperature):
        if False:  # pragma: no cover - generator typing
            yield ""
        raise self._exc


class FakeProviders:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def llm(self, name: str) -> LLMProvider:
        return self._llm


class FakeMemoryService:
    def __init__(self) -> None:
        self.enabled = False

    async def search_memories(self, **_kwargs) -> list[MemoryRecord]:
        return []

    async def add_memories(self, **_kwargs) -> None:
        return None


class FakeCharacters:
    def get(self, character_id: str):
        return SimpleNamespace(
            profile=SimpleNamespace(name="Tester"),
            to_system_prompt=lambda: "you are tester",
        )


@dataclass
class FakeSettings:
    default_llm_provider: str = "openai"
    default_tts_provider: str = "qwen"
    default_character_id: str = "luna"
    history_limit: int = 12
    memory_search_limit: int = 5
    memory_curator_provider: str | None = None


def _build_service(*, llm: LLMProvider, controls=None, safety=None) -> tuple[
    ChatTurnService, FakeStore, FakeBus, FakeControls
]:
    store = FakeStore()
    bus = FakeBus()
    fake_controls = controls or FakeControls()
    service = ChatTurnService(
        store=store,
        safety=safety or FakeSafety(),
        controls=fake_controls,
        events=bus,
        providers=FakeProviders(llm),
        agent_router=SelectiveAgentRouter(),
        agent_runtime=SimpleNamespace(),  # unused on the standard-LLM path
        memory_service=FakeMemoryService(),
        memory_curator=SimpleNamespace(),
        characters=FakeCharacters(),
        settings=FakeSettings(),
    )
    return service, store, bus, fake_controls


def _payload(message: str = "hello") -> ChatStreamRequest:
    return ChatStreamRequest(
        session_id="sess-test",
        session_token="token-test",
        user_id=1,
        message=message,
    )


async def _collect(service: ChatTurnService, payload: ChatStreamRequest) -> list[
    tuple[str, Any]
]:
    events = []
    async for name, data in service.run(payload=payload, user={"id": 1, "name": "tester", "bio": ""}):
        events.append((name, data))
    return events


# --- Tests ------------------------------------------------------------------


def test_happy_path_emits_start_delta_segment_done():
    service, store, bus, _ = _build_service(llm=FakeLLM(["hello! "]))
    events = asyncio.run(_collect(service, _payload()))
    names = [n for n, _ in events]

    assert names[0] == "start"
    assert "metric" in names  # llm_ttft_ms
    assert "delta" in names
    assert "segment" in names
    assert names[-1] == "done"

    done = events[-1][1]
    assert done.blocked is False
    assert done.text  # non-empty assistant reply persisted

    # User and assistant messages persisted exactly once each.
    roles = [row[1] for row in store.messages]
    assert roles == ["user", "assistant"]

    # Bus saw start/delta/segment/done but NOT metric (metrics are SSE-only).
    bus_names = [name for _, name in bus.published]
    assert "metric" not in bus_names
    assert {"start", "delta", "segment", "done"}.issubset(set(bus_names))


def test_safety_blocked_input_short_circuits():
    service, store, bus, _ = _build_service(
        llm=FakeLLM(["unreachable"]), safety=BlockingSafety()
    )
    events = asyncio.run(_collect(service, _payload()))
    names = [n for n, _ in events]

    assert names == ["error", "done"]
    err = events[0][1]
    assert isinstance(err, ErrorPayload)
    assert err.code == "safety_blocked"
    assert err.retryable is False
    assert events[1][1].blocked is True

    # Nothing persisted: no user message, no assistant message.
    assert store.messages == []
    assert store.errors and store.errors[0][1] == "safety_input"


def test_manual_stop_emits_stopped_and_returns_without_done():
    """Regression: prior code emitted `done` after `stopped` and persisted
    a partial assistant message. The fix must skip both."""
    controls = FakeControls(stop_after=1)  # stop before the second chunk
    service, store, bus, _ = _build_service(
        llm=FakeLLM(["one ", "two ", "three"]), controls=controls
    )
    events = asyncio.run(_collect(service, _payload()))
    names = [n for n, _ in events]

    assert "stopped" in names
    # Critical: no `done` event after `stopped`.
    assert "done" not in names
    assert names[-1] == "stopped"

    # Partial assistant message is NOT persisted.
    roles = [row[1] for row in store.messages]
    assert "assistant" not in roles

    # Bus saw the stopped event for stage subscribers.
    bus_names = [name for _, name in bus.published]
    assert "stopped" in bus_names


def test_provider_error_emits_retryable_error():
    service, store, _, _ = _build_service(
        llm=FailingLLM(ProviderError("upstream down"))
    )
    events = asyncio.run(_collect(service, _payload()))
    names = [n for n, _ in events]

    assert "error" in names
    err = next(data for n, data in events if n == "error")
    assert err.code == "llm_provider_unavailable"
    assert err.retryable is True
    # No `done` after a provider-error short-circuit.
    assert "done" not in names

    assert store.errors and store.errors[-1][1] == "llm"


def test_unhandled_exception_emits_server_error_with_request_id():
    service, _, _, _ = _build_service(llm=FailingLLM(RuntimeError("boom")))
    events = asyncio.run(_collect(service, _payload()))

    err = next(data for n, data in events if n == "error")
    assert err.code == "server_error"
    assert err.request_id and len(err.request_id) >= 8
    assert "done" not in [n for n, _ in events]
