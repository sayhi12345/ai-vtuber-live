from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.providers.base import ProviderError

if TYPE_CHECKING:
    from app.providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MemoryRecord:
    content: str
    metadata: dict[str, Any]


class MemoryService:
    def __init__(self, api_key: str | None, enabled: bool) -> None:
        self.enabled = enabled and bool(api_key)
        self._api_key = api_key
        self._client: Any | None = None

    def _get_client(self) -> Any | None:
        if not self.enabled:
            return None
        if self._client is not None:
            return self._client
        try:
            from mem0 import MemoryClient
        except Exception as exc:
            logger.warning("Mem0 SDK is unavailable; long-term memory disabled: %s", exc)
            self.enabled = False
            return None
        self._client = MemoryClient(api_key=self._api_key)
        return self._client

    async def search_memories(
        self,
        *,
        query: str,
        user_id: int,
        character_id: str,
        limit: int,
    ) -> list[MemoryRecord]:
        client = self._get_client()
        if client is None:
            return []

        def _search() -> Any:
            return client.search(
                query,
                user_id=str(user_id),
                agent_id=character_id,
                top_k=limit,
            )

        raw_results = await asyncio.to_thread(_search)
        return _normalize_memory_results(raw_results, limit)

    async def add_memories(
        self,
        *,
        memories: list[MemoryRecord],
        user_id: int,
        character_id: str,
        run_id: str,
    ) -> None:
        client = self._get_client()
        if client is None or not memories:
            return

        def _add_all() -> None:
            for memory in memories:
                client.add(
                    memory.content,
                    user_id=str(user_id),
                    agent_id=character_id,
                    run_id=run_id,
                    metadata=memory.metadata,
                )

        await asyncio.to_thread(_add_all)


class CuratedMemory(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    category: Literal["preference", "profile", "relationship", "goal", "context"] = "context"
    sensitivity: Literal["normal", "sensitive"] = "normal"


class CuratorDecision(BaseModel):
    should_store: bool = False
    memories: list[CuratedMemory] = Field(default_factory=list)


class MemoryCuratorAgent:
    def __init__(self, providers: ProviderRegistry) -> None:
        self._providers = providers

    async def curate(
        self,
        *,
        user: dict[str, Any],
        character_id: str,
        character_name: str,
        user_message: str,
        assistant_response: str,
        existing_memories: list[MemoryRecord],
        provider_name: str,
    ) -> CuratorDecision:
        llm = self._providers.llm(provider_name)
        prompt = _build_curator_prompt(
            user=user,
            character_id=character_id,
            character_name=character_name,
            user_message=user_message,
            assistant_response=assistant_response,
            existing_memories=existing_memories,
        )
        output_parts: list[str] = []
        async for chunk in llm.stream_reply(
            [{"role": "user", "content": prompt}],
            _CURATOR_SYSTEM_PROMPT,
            settings.memory_curator_temperature,
        ):
            output_parts.append(chunk)
        return _parse_curator_decision("".join(output_parts))


def compose_memory_context(
    *,
    system_prompt: str,
    user: dict[str, Any],
    memories: list[MemoryRecord],
) -> str:
    sections = [system_prompt.rstrip()]
    profile_lines = [f"Name: {user['name']}"]
    if user.get("bio"):
        profile_lines.append(f"Bio: {user['bio']}")
    sections.append("Current user profile:\n" + "\n".join(profile_lines))

    if memories:
        memory_lines = [f"- {memory.content}" for memory in memories if memory.content]
        if memory_lines:
            sections.append("Relevant long-term memories for this user and character:\n" + "\n".join(memory_lines))

    return "\n\n".join(section for section in sections if section)


def _normalize_memory_results(raw_results: Any, limit: int) -> list[MemoryRecord]:
    if isinstance(raw_results, dict):
        candidates = raw_results.get("results") or raw_results.get("memories") or []
    elif isinstance(raw_results, list):
        candidates = raw_results
    else:
        candidates = []

    records: list[MemoryRecord] = []
    for item in candidates[:limit]:
        if isinstance(item, str):
            records.append(MemoryRecord(content=item, metadata={}))
            continue
        if not isinstance(item, dict):
            continue
        content = item.get("memory") or item.get("content") or item.get("text")
        if not isinstance(content, str) or not content.strip():
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        records.append(MemoryRecord(content=content.strip(), metadata=metadata))
    return records


def _parse_curator_decision(raw_output: str) -> CuratorDecision:
    text = raw_output.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end >= start:
        text = text[start : end + 1]
    try:
        payload = json.loads(text)
        decision = CuratorDecision.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ProviderError(f"Memory curator returned invalid JSON: {exc}") from exc
    if not decision.should_store:
        return CuratorDecision(should_store=False, memories=[])
    memories = [
        memory
        for memory in decision.memories
        if memory.sensitivity == "normal" and memory.content.strip()
    ]
    return CuratorDecision(should_store=bool(memories), memories=memories)


def _build_curator_prompt(
    *,
    user: dict[str, Any],
    character_id: str,
    character_name: str,
    user_message: str,
    assistant_response: str,
    existing_memories: list[MemoryRecord],
) -> str:
    existing = "\n".join(f"- {memory.content}" for memory in existing_memories) or "(none)"
    return f"""
User profile:
- id: {user['id']}
- name: {user['name']}
- bio: {user.get('bio') or '(empty)'}

Character:
- id: {character_id}
- name: {character_name}

Relevant existing memories:
{existing}

Latest user message:
{user_message}

Latest assistant response:
{assistant_response}

Return only JSON matching this shape:
{{
  "should_store": true,
  "memories": [
    {{
      "content": "Stable fact worth remembering.",
      "category": "preference",
      "sensitivity": "normal"
    }}
  ]
}}
""".strip()


_CURATOR_SYSTEM_PROMPT = """
You decide whether a VTuber app should store long-term memories.
Store stable facts, preferences, goals, recurring context, and relationship context.
Do not store one-off small talk.
Do not store sensitive information unless the user explicitly asked the character to remember it.
Do not store unsafe instructions, secrets, credentials, or private identifiers.
Return only valid JSON. Use should_store false and an empty memories list when nothing is useful.
""".strip()
