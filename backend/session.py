"""Session store keyed by session ID — in-memory with upload history tracking."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

import pandas as pd


class SessionStore:
    """Thread-safe in-memory store for uploaded DataFrames and metadata."""

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}
        self._upload_history: list[dict] = []
        self._lock = Lock()

    def create(self, df: pd.DataFrame, filename: str, file_size: int = 0) -> str:
        session_id = uuid.uuid4().hex[:12]
        created = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._store[session_id] = {
                "df": df.copy(),
                "original_df": df.copy(),
                "filename": filename,
                "file_size": file_size,
                "created_at": created,
                "history": [],
            }
            self._upload_history.insert(0, {
                "session_id": session_id,
                "filename": filename,
                "file_size": file_size,
                "created_at": created,
                "status": "completed",
                "rows": len(df),
                "cols": len(df.columns),
            })
            # Keep only last 100 upload records
            if len(self._upload_history) > 100:
                self._upload_history = self._upload_history[:100]
        return session_id

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            entry = self._store.get(session_id)
            if entry is None:
                return None
            return {
                "df": entry["df"].copy(),
                "original_df": entry["original_df"].copy(),
                "filename": entry["filename"],
                "file_size": entry.get("file_size", 0),
                "created_at": entry["created_at"],
                "history": list(entry["history"]),
            }

    def update_df(self, session_id: str, df: pd.DataFrame, action: str) -> bool:
        with self._lock:
            entry = self._store.get(session_id)
            if entry is None:
                return False
            entry["df"] = df.copy()
            entry["history"].append(
                {"action": action, "at": datetime.now(timezone.utc).isoformat()}
            )
            return True

    def exists(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._store

    def get_upload_history(self) -> list[dict]:
        """Get upload history, newest first."""
        with self._lock:
            return list(self._upload_history)

    def delete(self, session_id: str) -> bool:
        """Remove a session."""
        with self._lock:
            if session_id in self._store:
                del self._store[session_id]
                return True
            return False


store = SessionStore()
