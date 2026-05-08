from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import urlparse

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings
from app.providers.base import LLMProvider, ProviderDescriptor, ProviderError
from app.providers.langchain_utils import build_langchain_messages, extract_text_content


def _gemini_api_endpoint(base_url: str) -> str:
    parsed = urlparse(base_url)
    return parsed.netloc or parsed.path or base_url


class GeminiProvider(LLMProvider):
    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise ProviderError("GEMINI_API_KEY is required for Gemini provider.")
        self._api_key = settings.gemini_api_key
        self._base_url = settings.gemini_base_url.rstrip("/")

    async def stream_reply(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        temperature: float,
    ) -> AsyncIterator[str]:
        prompt_messages = build_langchain_messages(messages, system_prompt)
        model_kwargs: dict[str, object] = {
            "model": settings.gemini_chat_model,
            "google_api_key": self._api_key,
            "temperature": temperature,
        }
        if self._base_url != "https://generativelanguage.googleapis.com":
            model_kwargs["client_options"] = {
                "api_endpoint": _gemini_api_endpoint(self._base_url)
            }

        chat_model = ChatGoogleGenerativeAI(**model_kwargs)

        try:
            async for chunk in chat_model.astream(prompt_messages):
                text = extract_text_content(chunk.content)
                if text:
                    yield text
        except Exception as exc:
            raise ProviderError(f"Gemini chat failed: {exc}") from exc


def _build_langchain_model(temperature: float) -> ChatGoogleGenerativeAI:
    base_url = settings.gemini_base_url.rstrip("/")
    model_kwargs: dict[str, object] = {
        "model": settings.gemini_chat_model,
        "google_api_key": settings.gemini_api_key,
        "temperature": temperature,
    }
    if base_url != "https://generativelanguage.googleapis.com":
        model_kwargs["client_options"] = {"api_endpoint": _gemini_api_endpoint(base_url)}
    return ChatGoogleGenerativeAI(**model_kwargs)


def register(registry) -> None:
    registry.register(
        ProviderDescriptor(
            name="gemini",
            factory=GeminiProvider,
            is_configured=lambda: bool(settings.gemini_api_key),
            supports_llm=True,
            langchain_factory=_build_langchain_model,
        )
    )
