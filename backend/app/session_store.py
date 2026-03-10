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
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
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
            self._conn.commit()

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with _locked(self._lock):
            self._conn.execute(
                """
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, now_iso()),
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
