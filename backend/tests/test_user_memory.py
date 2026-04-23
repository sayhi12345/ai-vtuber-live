from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.memory import _parse_curator_decision
from app.session_store import SessionStore


def test_user_crud_and_scoped_history(tmp_path: Path):
    store = SessionStore(str(tmp_path / "test.db"))
    luna_user = store.create_user("Shane", "Likes concise replies")
    other_user = store.create_user("Alex", "")

    assert store.list_users()[0]["id"] == other_user["id"]
    updated = store.update_user(luna_user["id"], bio="Likes relaxed divination")
    assert updated is not None
    assert updated["bio"] == "Likes relaxed divination"

    store.add_message("session-a", "user", "for luna", luna_user["id"], "luna")
    store.add_message("session-a", "assistant", "luna reply", luna_user["id"], "luna")
    store.add_message("session-b", "user", "for aria", luna_user["id"], "aria")
    store.add_message("session-c", "user", "other user", other_user["id"], "luna")

    assert store.get_scoped_history(luna_user["id"], "luna", 10) == [
        {"role": "user", "content": "for luna"},
        {"role": "assistant", "content": "luna reply"},
    ]


def test_curator_parser_filters_sensitive_memories():
    decision = _parse_curator_decision(
        """
        ```json
        {
          "should_store": true,
          "memories": [
            {"content": "User likes relaxed tarot readings.", "category": "preference", "sensitivity": "normal"},
            {"content": "User shared a secret token.", "category": "profile", "sensitivity": "sensitive"}
          ]
        }
        ```
        """
    )

    assert decision.should_store is True
    assert [memory.content for memory in decision.memories] == [
        "User likes relaxed tarot readings."
    ]


def test_chat_rejects_unknown_user_id(monkeypatch, tmp_path: Path):
    from app import main

    test_store = SessionStore(str(tmp_path / "test.db"))
    monkeypatch.setattr(main, "store", test_store)
    client = TestClient(main.app)

    response = client.post(
        "/api/chat/stream",
        json={
            "session_id": "session-test",
            "user_id": 999,
            "message": "hello",
            "llm_provider": "openai",
            "tts_provider": "openai",
            "character_id": "luna",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown user_id"
