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
from app.characters import load_default_registry
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
        self.messages: list[list[dict[str, str]]] = []
        self.system_prompts: list[str] = []

    async def stream_reply(self, messages, system_prompt, temperature):
        self.messages.append(list(messages))
        self.system_prompts.append(system_prompt)
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
            profile=SimpleNamespace(
                name="Tester",
                short_description="test character",
            ),
            to_system_prompt=lambda: "you are tester",
        )


@dataclass
class FakeSettings:
    default_llm_provider: str = "openai"
    default_tts_provider: str = "openai"
    default_character_id: str = "luna"
    history_limit: int = 12
    memory_search_limit: int = 5
    memory_curator_provider: str | None = None


def _build_service(
    *, llm: LLMProvider, controls=None, safety=None, characters=None
) -> tuple[ChatTurnService, FakeStore, FakeBus, FakeControls]:
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
        characters=characters or FakeCharacters(),
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


def test_chat_mode_is_default_and_does_not_add_game_instructions():
    llm = FakeLLM(["hello! "])
    service, _, _, _ = _build_service(llm=llm)

    asyncio.run(_collect(service, _payload()))

    assert _payload().mode == "chat"
    assert "共鳴挑戰" not in llm.system_prompts[0]


def test_harmony_challenge_preserves_each_persona_and_adds_scoring_contract():
    prompts = {}
    for character_id, persona_marker in (
        ("luna", "溫柔但偶爾毒舌"),
        ("aria", "活潑外向"),
    ):
        llm = FakeLLM(["challenge response! "])
        service, _, _, _ = _build_service(
            llm=llm,
            characters=load_default_registry(),
        )

        asyncio.run(
            _collect(
                service,
                ChatStreamRequest(
                    session_id=f"sess-{character_id}",
                    session_token="token-test",
                    user_id=1,
                    message="我的回應",
                    character_id=character_id,
                    mode="harmony_challenge",
                ),
            )
        )
        prompts[character_id] = llm.system_prompts[0]

        assert persona_marker in prompts[character_id]
        assert "共鳴挑戰" in prompts[character_id]
        assert "0-100" in prompts[character_id]
        assert "80" in prompts[character_id]
        assert "79" in prompts[character_id]
        assert "判定" in prompts[character_id]
        assert "角色反應" in prompts[character_id]
        assert "改進提示" in prompts[character_id]
        assert "輸出必須恰好四行，不得增加任何其他文字" in prompts[character_id]
        assert (
            "分數：<0-100 integer>\n"
            "判定：<成功|尚未成功>\n"
            "角色反應：<one short current emotion/reaction sentence>\n"
            "改進提示：<the only actionable suggestion>"
        ) in prompts[character_id]
        assert "不得告訴、要求、詢問或邀請使用者做任何事" in prompts[character_id]
        assert (
            "應該、可以、不妨、記得、下次、先、請、一起、建議、試試、考慮"
            in prompts[character_id]
        )

    assert prompts["luna"] != prompts["aria"]


def test_harmony_challenge_normalizes_malformed_output_before_emitting():
    cases = (
        (
            "luna",
            "露娜",
            "月之塔的神祕占卜師",
            "抱歉呢，這樣的行為似乎不太符合我作為占卜師的角色喔。\n"
            "你是否想知道這樣的決定會帶來什麼樣的結果呢？\n"
            "分數：45\n判定：尚未成功\n角色反應：我感受到一絲猶豫。\n"
            "改進提示：請提供更具象的問題。",
            45,
            "尚未成功",
            "抱歉呢",
        ),
        (
            "aria",
            "艾莉亞",
            "精力充沛的校園電競系 VTuber",
            "哇塞，這聽起來超刺激！翹課可得小心點喔！\n"
            "分數：85\n判定：成功\n角色反應：哇，好有冒險精神！",
            85,
            "成功",
            "哇塞",
        ),
        ("luna", "露娜", "月之塔的神祕占卜師", "分數：999", 100, "成功", "999"),
        ("aria", "艾莉亞", "精力充沛的校園電競系 VTuber", "分數：-12", 0, "尚未成功", "-12"),
        ("luna", "露娜", "月之塔的神祕占卜師", "完全沒有標示分數", 0, "尚未成功", "完全沒有"),
    )

    for character_id, name, description, malformed, score, verdict, leaked in cases:
        llm = FakeLLM([malformed])
        service, _, _, _ = _build_service(
            llm=llm,
            characters=load_default_registry(),
        )
        events = asyncio.run(
            _collect(
                service,
                ChatStreamRequest(
                    session_id=f"sess-normalize-{character_id}-{score}",
                    session_token="token-test",
                    user_id=1,
                    message="我的回應",
                    character_id=character_id,
                    mode="harmony_challenge",
                ),
            )
        )

        done_text = next(data.text for event, data in events if event == "done")
        reaction = (
            f"{name}被這番話打動了。"
            if score >= 80
            else f"{name}目前還沒有產生共鳴。"
        )
        lines = done_text.splitlines()
        assert [line.partition("：")[0] for line in lines] == [
            "分數",
            "判定",
            "主播反應",
            "改進提示",
        ]
        assert lines == [
            f"分數：{score}",
            f"判定：{verdict}",
            f"主播反應：{reaction}",
            f"改進提示：加入一個能呼應「{description}」的具體細節。",
        ]
        visible_text = "".join(
            data.text
            for event, data in events
            if event in {"delta", "segment", "done"}
        )
        assert leaked not in visible_text


def test_harmony_challenge_is_not_persisted():
    llm = FakeLLM(["reply! "])
    service, store, _, _ = _build_service(llm=llm)

    asyncio.run(
        _collect(
            service,
            ChatStreamRequest(
                session_id="sess-game",
                session_token="token-test",
                user_id=1,
                message="game answer",
                mode="harmony_challenge",
            ),
        )
    )

    assert store.messages == []
    assert llm.messages == [[{"role": "user", "content": "game answer"}]]


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
