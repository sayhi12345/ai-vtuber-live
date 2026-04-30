from __future__ import annotations

from collections.abc import AsyncIterator

from langchain_openai import ChatOpenAI

from app.config import settings
from app.providers.base import LLMProvider, ProviderError
from app.providers.langchain_utils import build_langchain_messages, extract_text_content


class LlamaCppProvider(LLMProvider):
    """Local llama.cpp server with OpenAI-compatible /v1/chat/completions.

    llama.cpp accepts any string as API key; we send a placeholder unless the
    user explicitly sets one (some setups put it behind a reverse proxy).
    """

    def __init__(self) -> None:
        if not settings.llamacpp_base_url:
            raise ProviderError("LLAMACPP_BASE_URL is required for llama.cpp provider.")
        self._api_key = settings.llamacpp_api_key or "sk-no-key-required"
        self._api_base_url = settings.llamacpp_base_url.rstrip("/")
        if not self._api_base_url.endswith("/v1"):
            self._api_base_url = f"{self._api_base_url}/v1"

    async def stream_reply(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        temperature: float,
    ) -> AsyncIterator[str]:
        prompt_messages = build_langchain_messages(messages, system_prompt)
        chat_model = ChatOpenAI(
            model=settings.llamacpp_chat_model,
            api_key=self._api_key,
            base_url=self._api_base_url,
            temperature=temperature,
            streaming=True,
        )

        try:
            async for chunk in chat_model.astream(prompt_messages):
                text = extract_text_content(chunk.content)
                if text:
                    yield text
        except Exception as exc:
            raise ProviderError(f"llama.cpp chat failed: {exc}") from exc
