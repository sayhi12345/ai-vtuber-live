from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
import sys
from typing import Any

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.agents.routing import AgentRouteDecision
from app.bazi import calculate_bazi_chart
from app.config import settings
from app.providers.base import ProviderError
from app.providers.gemini_provider import _gemini_api_endpoint
from app.providers.langchain_utils import extract_text_content
from app.providers.openai_provider import _normalize_openai_urls
from app.tarot import draw_tarot_cards

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = BACKEND_ROOT / "skills"


@tool
async def draw_tarot_cards_tool(question: str, spread: str = "three") -> dict[str, Any]:
    """Draw tarot cards for a reading and return a deterministic spread payload."""
    return await draw_tarot_cards(question=question, spread=spread)


@tool
async def calculate_bazi_chart_tool(
    year: int,
    month: int,
    day: int,
    hour: int,
    gender: str = "男",
) -> dict[str, Any]:
    """Calculate a bazi chart for the provided birth date, time, and gender ('男', '女')."""
    return calculate_bazi_chart(year=year, month=month, day=day, hour=hour, gender=gender)


class DeepAgentRuntime:
    async def stream_reply(
        self,
        *,
        route: AgentRouteDecision,
        provider_name: str,
        messages: list[dict[str, str]],
        system_prompt: str,
        temperature: float,
    ) -> AsyncIterator[str]:
        if not route.use_agent:
            raise ProviderError("Deep agent runtime requires a matched agent route.")

        agent = self._create_agent(
            route=route,
            provider_name=provider_name,
            system_prompt=system_prompt,
            temperature=temperature,
        )
        # Seed the stream cursor with the last assistant message from history so
        # the agent's first state does not replay the previous turn back to the client.
        last_text = _latest_assistant_text({"messages": messages})

        try:
            async for state in agent.astream({"messages": messages}, stream_mode="values"):
                current_text = _latest_assistant_text(state)
                if not current_text or current_text == last_text:
                    continue
                if current_text.startswith(last_text):
                    delta = current_text[len(last_text) :]
                else:
                    delta = current_text
                last_text = current_text
                if delta:
                    yield delta
        except Exception as exc:
            raise ProviderError(f"Deep agent failed: {exc}") from exc

    def _create_agent(
        self,
        *,
        route: AgentRouteDecision,
        provider_name: str,
        system_prompt: str,
        temperature: float,
    ) -> Any:
        create_deep_agent, backend_classes = _load_deepagents()
        return create_deep_agent(
            model=_build_agent_model(provider_name, temperature),
            system_prompt=_compose_agent_system_prompt(system_prompt, route),
            backend=_build_backend_factory(backend_classes),
            skills=route.skill_sources,
            tools=[draw_tarot_cards_tool, calculate_bazi_chart_tool],
        )


def _build_agent_model(provider_name: str, temperature: float) -> Any:
    normalized = provider_name.lower()
    if normalized == "openai":
        _, api_base_url = _normalize_openai_urls(settings.openai_base_url.rstrip("/"))
        return ChatOpenAI(
            model=settings.openai_chat_model,
            api_key=settings.openai_api_key,
            base_url=api_base_url,
            temperature=temperature,
            streaming=True,
        )
    if normalized == "gemini":
        model_kwargs: dict[str, object] = {
            "model": settings.gemini_chat_model,
            "google_api_key": settings.gemini_api_key,
            "temperature": temperature,
        }
        if settings.gemini_base_url.rstrip("/") != "https://generativelanguage.googleapis.com":
            model_kwargs["client_options"] = {
                "api_endpoint": _gemini_api_endpoint(settings.gemini_base_url.rstrip("/"))
            }
        return ChatGoogleGenerativeAI(**model_kwargs)
    raise ProviderError(f"Unsupported LLM provider for deep agent routing: {provider_name}")


def _load_deepagents() -> tuple[Any, dict[str, Any]]:
    if sys.version_info < (3, 11):
        version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        raise ProviderError(
            f"deepagents requires Python 3.11+; current backend runtime is Python {version}."
        )
    try:
        from deepagents import create_deep_agent
        from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
    except ImportError as exc:  # pragma: no cover - optional dependency at runtime
        raise ProviderError(
            "deepagents is not installed. Install backend requirements in a Python 3.11+ environment to use agent skills."
        ) from exc
    return create_deep_agent, {
        "CompositeBackend": CompositeBackend,
        "FilesystemBackend": FilesystemBackend,
        "StateBackend": StateBackend,
    }


def _build_backend_factory(backend_classes: dict[str, Any]) -> Any:
    composite_backend_cls = backend_classes["CompositeBackend"]
    filesystem_backend_cls = backend_classes["FilesystemBackend"]
    state_backend_cls = backend_classes["StateBackend"]

    return lambda runtime: composite_backend_cls(
        default=state_backend_cls(runtime),
        routes={
            "/skills/": filesystem_backend_cls(
                root_dir=str(SKILLS_ROOT),
                virtual_mode=True,
            ),
        },
    )


def _compose_agent_system_prompt(system_prompt: str, route: AgentRouteDecision) -> str:
    if not route.runtime_instructions:
        return system_prompt
    return f"{system_prompt}\n\n{route.runtime_instructions}"


def _latest_assistant_text(state: Any) -> str:
    if not isinstance(state, dict):
        return ""
    messages = state.get("messages")
    if not isinstance(messages, list):
        return ""

    for message in reversed(messages):
        message_type = _message_type(message)
        if message_type not in {"ai", "assistant"}:
            continue
        content = getattr(message, "content", None)
        if content is None and isinstance(message, dict):
            content = message.get("content")
        text = extract_text_content(content)
        if text:
            return text
    return ""


def _message_type(message: Any) -> str | None:
    if isinstance(message, dict):
        for key in ("role", "type"):
            value = message.get(key)
            if isinstance(value, str):
                return value
        return None
    value = getattr(message, "type", None)
    if isinstance(value, str):
        return value
    return None
