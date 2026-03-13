from __future__ import annotations

import asyncio

from app.agents.routing import SelectiveAgentRouter
from app.agents.runtime import DeepAgentRuntime, _compose_agent_system_prompt, _latest_assistant_text


class _FakeMessage:
    def __init__(self, message_type: str, content: str) -> None:
        self.type = message_type
        self.content = content


class _FakeAgent:
    async def astream(self, *_args, **_kwargs):
        yield {"messages": [_FakeMessage("human", "hi")]}
        yield {"messages": [_FakeMessage("ai", "你好")]}
        yield {"messages": [_FakeMessage("ai", "你好，現在一起看這個牌陣。")]}


def test_selective_router_routes_tarot_queries_to_agent():
    router = SelectiveAgentRouter()

    decision = router.decide("幫我抽三張塔羅牌看感情")

    assert decision.use_agent is True
    assert decision.mode == "tarot"
    assert decision.skill_names == ["tarot"]
    assert decision.skill_sources == ["/skills/tarot"]
    assert "draw_tarot_cards_tool" in decision.runtime_instructions


def test_selective_router_leaves_regular_chat_on_standard_path():
    router = SelectiveAgentRouter()

    decision = router.decide("幫我寫一段 FastAPI middleware")

    assert decision.use_agent is False
    assert decision.mode == "chat"
    assert decision.skill_names == []


def test_selective_router_logs_tarot_queries(caplog):
    caplog.set_level("INFO")
    router = SelectiveAgentRouter()

    decision = router.decide("幫我抽三張塔羅牌看感情")

    assert decision.mode == "tarot"
    assert "Selective agent router observed divination-related query" in caplog.text
    assert "mode=tarot" in caplog.text


def test_selective_router_logs_fortune_queries_without_skill_match(caplog):
    caplog.set_level("INFO")
    router = SelectiveAgentRouter()

    decision = router.decide("可以幫我算命看今年的工作運勢嗎")

    assert decision.mode == "chat"
    assert decision.skill_names == []
    assert "Selective agent router observed divination-related query" in caplog.text
    assert "mode=chat" in caplog.text


def test_latest_assistant_text_reads_langchain_message_content():
    state = {
        "messages": [
            _FakeMessage("human", "hi"),
            _FakeMessage("ai", "第一段"),
        ]
    }

    assert _latest_assistant_text(state) == "第一段"


def test_compose_agent_system_prompt_appends_runtime_compat_rules():
    router = SelectiveAgentRouter()
    decision = router.decide("幫我抽一張塔羅牌")

    prompt = _compose_agent_system_prompt("你是一位 AI VTuber。", decision)

    assert "你是一位 AI VTuber。" in prompt
    assert "Tarot skill compatibility rules" in prompt
    assert "/skills/tarot" in prompt


def test_deep_agent_runtime_streams_only_new_text(monkeypatch):
    runtime = DeepAgentRuntime()
    router = SelectiveAgentRouter()
    decision = router.decide("幫我抽三張塔羅牌")

    captured: dict[str, object] = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return _FakeAgent()

    monkeypatch.setattr(runtime, "_create_agent", fake_create_agent)

    async def collect() -> list[str]:
        return [
            chunk
            async for chunk in runtime.stream_reply(
                route=decision,
                provider_name="openai",
                messages=[{"role": "user", "content": "幫我抽三張塔羅牌"}],
                system_prompt="你是一位 AI VTuber。",
                temperature=0.3,
            )
        ]

    chunks = asyncio.run(collect())

    assert chunks == ["你好", "，現在一起看這個牌陣。"]
    assert captured["provider_name"] == "openai"
    assert captured["temperature"] == 0.3
