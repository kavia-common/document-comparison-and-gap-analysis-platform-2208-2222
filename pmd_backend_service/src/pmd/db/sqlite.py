from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SQLiteConfig:
    """SQLite config resolved from environment."""

    db_path: str


class SQLiteDB:
    """Tiny SQLite helper for this service.

    Uses sqlite3 directly (no ORM) to keep dependencies minimal and predictable.
    """

    def __init__(self, config: SQLiteConfig):
        self._config = config
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._config.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                # Runs table: stores payloads as JSON strings for flexibility.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pmd_runs (
                        run_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        error TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        template_json TEXT NOT NULL,
                        inventory_json TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        matching_json TEXT,
                        gap_analysis_json TEXT,
                        generated_pmd_json TEXT
                    )
                    """
                )
                # Placeholder uploads (future: actual file storage).
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS placeholder_uploads (
                        upload_id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        content_type TEXT,
                        notes TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def insert_placeholder_upload(
        self, filename: str, content_type: Optional[str], notes: Optional[str]
    ) -> str:
        upload_id = str(uuid.uuid4())
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO placeholder_uploads (upload_id, filename, content_type, notes, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (upload_id, filename, content_type, notes, _utc_now_iso()),
                )
                conn.commit()
            finally:
                conn.close()
        return upload_id

    def insert_run(
        self,
        *,
        run_id: str,
        status: str,
        template: Any,
        inventory: Any,
        metadata: Dict[str, Any],
    ) -> None:
        now = _utc_now_iso()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO pmd_runs (
                        run_id, status, error, created_at, updated_at,
                        template_json, inventory_json, metadata_json,
                        matching_json, gap_analysis_json, generated_pmd_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        status,
                        None,
                        now,
                        now,
                        json.dumps(template),
                        json.dumps(inventory),
                        json.dumps(metadata or {}),
                        None,
                        None,
                        None,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def update_run_status(self, run_id: str, status: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE pmd_runs
                    SET status = ?, updated_at = ?
                    WHERE run_id = ?
                    """,
                    (status, _utc_now_iso(), run_id),
                )
                conn.commit()
            finally:
                conn.close()

    def update_run_error(self, run_id: str, error: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE pmd_runs
                    SET error = ?, updated_at = ?
                    WHERE run_id = ?
                    """,
                    (error, _utc_now_iso(), run_id),
                )
                conn.commit()
            finally:
                conn.close()

    def update_run_result_json(self, run_id: str, *, field: str, value: Any) -> None:
        if field not in {"matching_json", "gap_analysis_json", "generated_pmd_json"}:
            raise ValueError(f"Unsupported field: {field}")

        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    f"""
                    UPDATE pmd_runs
                    SET {field} = ?, updated_at = ?
                    WHERE run_id = ?
                    """,
                    (json.dumps(value), _utc_now_iso(), run_id),
                )
                conn.commit()
            finally:
                conn.close()

    def fetch_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM pmd_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def list_runs(self, *, limit: int, offset: int) -> list[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM pmd_runs
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()


_DB_SINGLETON: Optional[SQLiteDB] = None


def _resolve_config() -> SQLiteConfig:
    # IMPORTANT: env var is provided by the SQLite container integration.
    # Ask orchestrator/user to set SQLITE_DB in .env if missing.
    db_path = os.getenv("SQLITE_DB")
    if not db_path:
        # Fall back to local file for dev, but still encourage proper env configuration.
        db_path = os.path.abspath("myapp.db")
    return SQLiteConfig(db_path=db_path)


# PUBLIC_INTERFACE
def get_db() -> SQLiteDB:
    """Get singleton SQLiteDB instance.

    Returns:
        SQLiteDB initialized with schema.
    """
    global _DB_SINGLETON
    if _DB_SINGLETON is None:
        _DB_SINGLETON = SQLiteDB(_resolve_config())
    return _DB_SINGLETON
