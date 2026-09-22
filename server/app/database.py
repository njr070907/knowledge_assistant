from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._initialize()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT,
                    platform TEXT,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    ended_at TEXT,
                    subject TEXT,
                    summary_markdown TEXT,
                    notion_page_id TEXT,
                    sync_status TEXT NOT NULL DEFAULT 'not_configured',
                    sync_error TEXT
                );
                CREATE TABLE IF NOT EXISTS transcripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    start_seconds REAL NOT NULL,
                    end_seconds REAL NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                CREATE TABLE IF NOT EXISTS learning_marks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    video_seconds REAL NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                CREATE TABLE IF NOT EXISTS knowledge_cards (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    key_points_json TEXT NOT NULL,
                    question TEXT NOT NULL,
                    start_seconds REAL NOT NULL,
                    end_seconds REAL NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                CREATE TABLE IF NOT EXISTS sync_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                """
            )
        self._ensure_session_columns()

    def _ensure_session_columns(self) -> None:
        existing = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(sessions)").fetchall()
        }
        additions = {
            "subject": "TEXT",
            "summary_markdown": "TEXT",
            "notion_page_id": "TEXT",
            "sync_status": "TEXT NOT NULL DEFAULT 'not_configured'",
            "sync_error": "TEXT",
        }
        with self._connection:
            for name, definition in additions.items():
                if name not in existing:
                    self._connection.execute(f"ALTER TABLE sessions ADD COLUMN {name} {definition}")

    def start_session(self, session_id: str, title: str, url: str | None, platform: str | None) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO sessions (id, title, url, platform) VALUES (?, ?, ?, ?)",
                (session_id, title, url, platform),
            )

    def add_transcript(self, session_id: str, start: float, end: float, text: str) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "INSERT INTO transcripts (session_id, start_seconds, end_seconds, text) VALUES (?, ?, ?, ?)",
                (session_id, start, end, text),
            )
            return int(cursor.lastrowid)

    def recent_transcripts(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, start_seconds, end_seconds, text FROM transcripts WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def all_transcripts(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, start_seconds, end_seconds, text FROM transcripts WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def add_knowledge_card(self, session_id: str, card: dict[str, Any]) -> None:
        import json

        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO knowledge_cards
                (id, session_id, subject, title, summary, key_points_json, question,
                 start_seconds, end_seconds, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card["id"],
                    session_id,
                    card["subject"],
                    card["title"],
                    card["summary"],
                    json.dumps(card.get("keyPoints", []), ensure_ascii=False),
                    card["question"],
                    card["start"],
                    card["end"],
                    card.get("source", "local-rules"),
                ),
            )

    def knowledge_cards(self, session_id: str) -> list[dict[str, Any]]:
        import json

        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM knowledge_cards WHERE session_id = ? ORDER BY start_seconds",
                (session_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["key_points"] = json.loads(item.pop("key_points_json"))
            result.append(item)
        return result

    def add_mark(self, session_id: str, kind: str, video_seconds: float, note: str | None = None) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "INSERT INTO learning_marks (session_id, kind, video_seconds, note) VALUES (?, ?, ?, ?)",
                (session_id, kind, video_seconds, note),
            )
            return int(cursor.lastrowid)

    def finish_session(self, session_id: str, subject: str, markdown: str, sync_status: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE sessions
                SET ended_at = CURRENT_TIMESTAMP, subject = ?, summary_markdown = ?, sync_status = ?, sync_error = NULL
                WHERE id = ?
                """,
                (subject, markdown, sync_status, session_id),
            )

    def enqueue_sync(self, session_id: str, provider: str, payload: str) -> int:
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT id FROM sync_jobs WHERE session_id = ? AND provider = ? AND status IN ('pending', 'running', 'failed') ORDER BY id DESC LIMIT 1",
                (session_id, provider),
            ).fetchone()
            if existing:
                return int(existing["id"])
            cursor = self._connection.execute(
                "INSERT INTO sync_jobs (session_id, provider, payload) VALUES (?, ?, ?)",
                (session_id, provider, payload),
            )
            return int(cursor.lastrowid)

    def pending_sync_jobs(self, provider: str = "notion", limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM sync_jobs WHERE provider = ? AND status IN ('pending', 'failed') AND attempts < 5 ORDER BY id LIMIT ?",
                (provider, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_sync_job(self, job_id: int, status: str, error: str | None = None) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE sync_jobs
                SET status = ?, attempts = attempts + CASE WHEN ? = 'running' THEN 1 ELSE 0 END,
                    last_error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, status, error, job_id),
            )

    def set_notion_result(self, session_id: str, status: str, page_id: str | None = None, error: str | None = None) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE sessions SET sync_status = ?, notion_page_id = COALESCE(?, notion_page_id), sync_error = ? WHERE id = ?",
                (status, page_id, error, session_id),
            )
