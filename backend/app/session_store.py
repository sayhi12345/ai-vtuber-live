from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _locked(lock: threading.Lock):
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


class SessionStore:
    def __init__(self, sqlite_path: str) -> None:
        db_path = Path(sqlite_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_tables()

    def _init_tables(self) -> None:
        with _locked(self._lock):
            cursor = self._conn.cursor()
            cursor.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    bio TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_id INTEGER,
                    character_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session_created
                ON messages (session_id, created_at);

                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    value_ms REAL NOT NULL,
                    provider TEXT,
                    meta_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL,
                    meta_json TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            existing_message_columns = {
                row["name"] for row in cursor.execute("PRAGMA table_info(messages)").fetchall()
            }
            if "user_id" not in existing_message_columns:
                cursor.execute("ALTER TABLE messages ADD COLUMN user_id INTEGER")
            if "character_id" not in existing_message_columns:
                cursor.execute("ALTER TABLE messages ADD COLUMN character_id TEXT")
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_user_character_created
                ON messages (user_id, character_id, created_at)
                """
            )
            self._conn.commit()

    def create_user(self, name: str, bio: str = "") -> dict[str, Any]:
        timestamp = now_iso()
        clean_name = name.strip()
        clean_bio = bio.strip()
        with _locked(self._lock):
            cursor = self._conn.execute(
                """
                INSERT INTO users (name, bio, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (clean_name, clean_bio, timestamp, timestamp),
            )
            self._conn.commit()
            user_id = int(cursor.lastrowid)
        return {
            "id": user_id,
            "name": clean_name,
            "bio": clean_bio,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def list_users(self) -> list[dict[str, Any]]:
        with _locked(self._lock):
            rows = self._conn.execute(
                """
                SELECT id, name, bio, created_at, updated_at
                FROM users
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._user_from_row(row) for row in rows]

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        with _locked(self._lock):
            row = self._conn.execute(
                """
                SELECT id, name, bio, created_at, updated_at
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return self._user_from_row(row)

    def update_user(
        self,
        user_id: int,
        *,
        name: str | None = None,
        bio: str | None = None,
    ) -> dict[str, Any] | None:
        existing = self.get_user(user_id)
        if existing is None:
            return None

        next_name = existing["name"] if name is None else name.strip()
        next_bio = existing["bio"] if bio is None else bio.strip()
        updated_at = now_iso()
        with _locked(self._lock):
            self._conn.execute(
                """
                UPDATE users
                SET name = ?, bio = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_name, next_bio, updated_at, user_id),
            )
            self._conn.commit()
        return {**existing, "name": next_name, "bio": next_bio, "updated_at": updated_at}

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: int | None = None,
        character_id: str | None = None,
    ) -> None:
        with _locked(self._lock):
            self._conn.execute(
                """
                INSERT INTO messages (session_id, user_id, character_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, user_id, character_id, role, content, now_iso()),
            )
            self._conn.commit()

    def get_history(self, session_id: str, limit: int) -> list[dict[str, str]]:
        with _locked(self._lock):
            rows = self._conn.execute(
                """
                SELECT role, content
                FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        history = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        return history

    def get_scoped_history(
        self,
        user_id: int,
        character_id: str,
        limit: int,
    ) -> list[dict[str, str]]:
        with _locked(self._lock):
            rows = self._conn.execute(
                """
                SELECT role, content
                FROM messages
                WHERE user_id = ? AND character_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, character_id, limit),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    def _user_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "bio": row["bio"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def reset_session(self, session_id: str) -> None:
        with _locked(self._lock):
            self._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM metrics WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM errors WHERE session_id = ?", (session_id,))
            self._conn.commit()

    def log_metric(
        self,
        session_id: str,
        event: str,
        value_ms: float,
        provider: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        with _locked(self._lock):
            self._conn.execute(
                """
                INSERT INTO metrics (session_id, event, value_ms, provider, meta_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, event, value_ms, provider, meta_json, now_iso()),
            )
            self._conn.commit()

    def log_error(
        self,
        session_id: str,
        stage: str,
        message: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        with _locked(self._lock):
            self._conn.execute(
                """
                INSERT INTO errors (session_id, stage, message, meta_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, stage, message, meta_json, now_iso()),
            )
            self._conn.commit()

    def recent_metrics(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with _locked(self._lock):
            rows = self._conn.execute(
                """
                SELECT event, value_ms, provider, meta_json, created_at
                FROM metrics
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [
            {
                "event": row["event"],
                "value_ms": row["value_ms"],
                "provider": row["provider"],
                "meta": json.loads(row["meta_json"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]


class SessionControl:
    def __init__(self) -> None:
        self._stop_flags: dict[str, bool] = defaultdict(bool)
        self._mute_flags: dict[str, bool] = defaultdict(bool)
        self._lock = threading.Lock()

    def request_stop(self, session_id: str) -> None:
        with _locked(self._lock):
            self._stop_flags[session_id] = True

    def clear_stop(self, session_id: str) -> None:
        with _locked(self._lock):
            self._stop_flags[session_id] = False

    def should_stop(self, session_id: str) -> bool:
        with _locked(self._lock):
            return self._stop_flags.get(session_id, False)

    def set_mute(self, session_id: str, muted: bool) -> None:
        with _locked(self._lock):
            self._mute_flags[session_id] = muted

    def is_muted(self, session_id: str) -> bool:
        with _locked(self._lock):
            return self._mute_flags.get(session_id, False)


@dataclass
class StageEvent:
    event: str
    payload: dict[str, Any]


class SessionEventBus:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[StageEvent]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, session_id: str) -> asyncio.Queue[StageEvent]:
        queue: asyncio.Queue[StageEvent] = asyncio.Queue(maxsize=128)
        async with self._lock:
            self._queues[session_id].append(queue)
        return queue

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue[StageEvent]) -> None:
        async with self._lock:
            queues = self._queues.get(session_id, [])
            if queue in queues:
                queues.remove(queue)
            if not queues and session_id in self._queues:
                del self._queues[session_id]

    async def publish(self, session_id: str, event: StageEvent) -> None:
        async with self._lock:
            queues = list(self._queues.get(session_id, []))
        for queue in queues:
            if queue.full():
                try:
                    _ = queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await queue.put(event)
