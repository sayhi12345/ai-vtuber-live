from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.providers.base import ProviderError
from app.providers.langchain_utils import build_langchain_messages, extract_text_content


def test_build_langchain_messages_includes_system_prompt():
    messages = build_langchain_messages(
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
        "stay concise",
    )

    assert isinstance(messages[0], SystemMessage)
    assert messages[0].content == "stay concise"
    assert isinstance(messages[1], HumanMessage)
    assert messages[1].content == "hello"
    assert isinstance(messages[2], AIMessage)
    assert messages[2].content == "hi"


def test_build_langchain_messages_rejects_unknown_role():
    try:
        build_langchain_messages([{"role": "tool", "content": "x"}], "")
    except ProviderError as exc:
        assert "Unsupported chat message role" in str(exc)
    else:
        raise AssertionError("Expected ProviderError for unsupported role")


def test_extract_text_content_handles_block_payloads():
    text = extract_text_content(
        [
            {"type": "text", "text": "你"},
            {"type": "text", "text": "好"},
            {"type": "ignored", "foo": "bar"},
        ]
    )

    assert text == "你好"
