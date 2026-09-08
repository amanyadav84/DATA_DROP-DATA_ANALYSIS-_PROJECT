"""Chunked upload manager — handles chunk assembly, resume tracking, and temp storage."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Optional

from config import TEMP_UPLOAD_DIR, get_chunk_size


class UploadChunk:
    """Represents a single chunk of an upload."""

    def __init__(self, upload_id: str, chunk_number: int, total_chunks: int):
        self.upload_id = upload_id
        self.chunk_number = chunk_number
        self.total_chunks = total_chunks
        self.received_at = time.time()


class UploadSession:
    """Tracks the state of a chunked upload."""

    def __init__(
        self,
        upload_id: str,
        filename: str,
        file_size: int,
        total_chunks: int,
        file_hash: str = "",
    ):
        self.upload_id = upload_id
        self.filename = filename
        self.file_size = file_size
        self.total_chunks = total_chunks
        self.file_hash = file_hash
        self.chunks_received: set[int] = set()
        self.created_at = time.time()
        self.completed = False
        self.assembled = False
        self.error: Optional[str] = None
        self.upload_dir: Optional[Path] = None

    @property
    def progress_pct(self) -> float:
        if self.total_chunks == 0:
            return 0.0
        return round(len(self.chunks_received) / self.total_chunks * 100, 1)

    @property
    def bytes_received(self) -> int:
        return len(self.chunks_received) * get_chunk_size()

    def to_dict(self) -> dict:
        return {
            "upload_id": self.upload_id,
            "filename": self.filename,
            "file_size": self.file_size,
            "total_chunks": self.total_chunks,
            "file_hash": self.file_hash,
            "chunks_received": sorted(self.chunks_received),
            "progress_pct": self.progress_pct,
            "bytes_received": self.bytes_received,
            "created_at": self.created_at,
            "completed": self.completed,
            "assembled": self.assembled,
            "error": self.error,
        }


class ChunkedUploadManager:
    """Thread-safe manager for chunked file uploads."""

    def __init__(self):
        self._sessions: dict[str, UploadSession] = {}
        self._lock = Lock()
        # Ensure temp directory exists
        TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    def create_session(
        self,
        filename: str,
        file_size: int,
        total_chunks: int,
        file_hash: str = "",
    ) -> UploadSession:
        """Create a new chunked upload session."""
        upload_id = uuid.uuid4().hex[:16]
        session = UploadSession(
            upload_id=upload_id,
            filename=filename,
            file_size=file_size,
            total_chunks=total_chunks,
            file_hash=file_hash,
        )
        # Create upload directory
        upload_dir = TEMP_UPLOAD_DIR / upload_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        session.upload_dir = upload_dir
        with self._lock:
            self._sessions[upload_id] = session
        return session

    def get_session(self, upload_id: str) -> Optional[UploadSession]:
        """Get an upload session by ID."""
        with self._lock:
            return self._sessions.get(upload_id)

    def receive_chunk(
        self,
        upload_id: str,
        chunk_number: int,
        chunk_data: bytes,
        total_chunks: int,
    ) -> dict:
        """Receive and store a chunk. Returns status dict."""
        session = self.get_session(upload_id)
        if session is None:
            return {"error": "Upload session not found", "status": "error"}

        if session.completed:
            return {"error": "Upload already completed", "status": "error"}

        # Update total_chunks if it changed
        if total_chunks != session.total_chunks:
            with self._lock:
                session.total_chunks = total_chunks

        # Store chunk
        chunk_path = session.upload_dir / f"chunk_{chunk_number:06d}"
        chunk_path.write_bytes(chunk_data)

        with self._lock:
            session.chunks_received.add(chunk_number)

        return {
            "status": "ok",
            "chunk_number": chunk_number,
            "chunks_received": len(session.chunks_received),
            "total_chunks": session.total_chunks,
            "progress_pct": session.progress_pct,
            "upload_id": upload_id,
        }

    def is_complete(self, upload_id: str) -> bool:
        """Check if all chunks have been received."""
        session = self.get_session(upload_id)
        if session is None:
            return False
        return len(session.chunks_received) >= session.total_chunks

    def assemble_file(self, upload_id: str) -> Optional[Path]:
        """Assemble chunks into the final file. Returns file path or None."""
        session = self.get_session(upload_id)
        if session is None:
            return None

        if session.assembled:
            # Return existing assembled file
            assembled = session.upload_dir / session.filename
            if assembled.exists():
                return assembled

        assembled = session.upload_dir / session.filename
        try:
            with open(assembled, "wb") as out:
                for i in range(session.total_chunks):
                    chunk_path = session.upload_dir / f"chunk_{i:06d}"
                    if chunk_path.exists():
                        out.write(chunk_path.read_bytes())
                    else:
                        raise IOError(f"Missing chunk {i}")

            # Remove individual chunks
            for i in range(session.total_chunks):
                chunk_path = session.upload_dir / f"chunk_{i:06d}"
                if chunk_path.exists():
                    chunk_path.unlink()

            with self._lock:
                session.assembled = True
                session.completed = True

            return assembled
        except Exception as e:
            with self._lock:
                session.error = str(e)
            return None

    def get_missing_chunks(self, upload_id: str) -> list[int]:
        """Get list of missing chunk numbers for resume support."""
        session = self.get_session(upload_id)
        if session is None:
            return []
        return sorted(set(range(session.total_chunks)) - session.chunks_received)

    def cancel_upload(self, upload_id: str) -> bool:
        """Cancel and clean up an upload session."""
        session = self.get_session(upload_id)
        if session is None:
            return False

        if session.upload_dir and session.upload_dir.exists():
            shutil.rmtree(session.upload_dir, ignore_errors=True)

        with self._lock:
            del self._sessions[upload_id]
        return True

    def cleanup_stale(self, max_age_hours: int = 24) -> int:
        """Remove sessions older than max_age_hours. Returns count removed."""
        cutoff = time.time() - (max_age_hours * 3600)
        stale_ids = []
        with self._lock:
            for uid, session in self._sessions.items():
                if session.created_at < cutoff:
                    stale_ids.append(uid)

        for uid in stale_ids:
            self.cancel_upload(uid)

        return len(stale_ids)

    def get_active_sessions(self) -> list[dict]:
        """Get all active (incomplete) upload sessions."""
        with self._lock:
            return [
                s.to_dict()
                for s in self._sessions.values()
                if not s.completed
            ]


# Singleton instance
chunk_manager = ChunkedUploadManager()
