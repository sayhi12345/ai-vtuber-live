from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.providers.base import ProviderError


def build_langchain_messages(
    messages: list[dict[str, str]],
    system_prompt: str,
) -> list[SystemMessage | HumanMessage | AIMessage]:
    prompt_messages: list[SystemMessage | HumanMessage | AIMessage] = []
    if system_prompt:
        prompt_messages.append(SystemMessage(content=system_prompt))

    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if role == "user":
            prompt_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            prompt_messages.append(AIMessage(content=content))
        elif role == "system":
            prompt_messages.append(SystemMessage(content=content))
        else:
            raise ProviderError(f"Unsupported chat message role: {role}")

    return prompt_messages


def extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
                continue
            if not isinstance(part, dict):
                continue

            text = part.get("text")
            if isinstance(text, str):
                text_parts.append(text)
                continue

            for key in ("content", "output_text"):
                value = part.get(key)
                if isinstance(value, str):
                    text_parts.append(value)
                    break

        return "".join(text_parts)

    return ""
