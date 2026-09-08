"""In-memory project store for organizing datasets, dashboards, and analysis."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Any


class ProjectStore:
    """Thread-safe in-memory store for projects."""

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}
        self._lock = Lock()

    def create(self, name: str, description: str = "", settings: dict | None = None) -> dict:
        project_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        project = {
            "id": project_id,
            "name": name,
            "description": description,
            "created_at": now,
            "updated_at": now,
            "datasets": [],
            "dashboards": [],
            "settings": settings or {},
            "status": "active",
            "tags": [],
            "activity_log": [{
                "action": "project_created",
                "details": f"Project '{name}' created",
                "timestamp": now,
            }],
        }
        with self._lock:
            self._store[project_id] = project
        return project.copy()

    def get(self, project_id: str) -> dict | None:
        with self._lock:
            project = self._store.get(project_id)
            if project is None:
                return None
            return project.copy()

    def list_projects(self, status: str | None = None) -> list[dict]:
        with self._lock:
            results = []
            for project in self._store.values():
                if status and project.get("status") != status:
                    continue
                results.append({
                    "id": project.get("id"),
                    "name": project.get("name"),
                    "description": project.get("description"),
                    "created_at": project.get("created_at"),
                    "updated_at": project.get("updated_at"),
                    "status": project.get("status"),
                    "dataset_count": len(project.get("datasets", [])),
                    "dashboard_count": len(project.get("dashboards", [])),
                    "tags": project.get("tags", []),
                })
            return sorted(results, key=lambda x: x.get("updated_at", ""), reverse=True)

    def update(self, project_id: str, updates: dict) -> dict | None:
        with self._lock:
            project = self._store.get(project_id)
            if project is None:
                return None
            now = datetime.now(timezone.utc).isoformat()
            for key in ("name", "description", "settings", "status", "tags"):
                if key in updates:
                    project[key] = updates[key]
            project["updated_at"] = now
            project["activity_log"].append({
                "action": "project_updated",
                "details": f"Project updated: {', '.join(updates.keys())}",
                "timestamp": now,
            })
            return project.copy()

    def delete(self, project_id: str) -> bool:
        with self._lock:
            if project_id in self._store:
                del self._store[project_id]
                return True
            return False

    def add_dataset(self, project_id: str, session_id: str, filename: str) -> dict | None:
        with self._lock:
            project = self._store.get(project_id)
            if project is None:
                return None
            if session_id in [d["session_id"] for d in project["datasets"]]:
                return project.copy()
            now = datetime.now(timezone.utc).isoformat()
            project["datasets"].append({
                "session_id": session_id,
                "filename": filename,
                "added_at": now,
            })
            project["updated_at"] = now
            project["activity_log"].append({
                "action": "dataset_added",
                "details": f"Dataset '{filename}' added to project",
                "timestamp": now,
            })
            return project.copy()

    def remove_dataset(self, project_id: str, session_id: str) -> dict | None:
        with self._lock:
            project = self._store.get(project_id)
            if project is None:
                return None
            original_count = len(project["datasets"])
            project["datasets"] = [d for d in project["datasets"] if d["session_id"] != session_id]
            if len(project["datasets"]) < original_count:
                now = datetime.now(timezone.utc).isoformat()
                project["updated_at"] = now
                project["activity_log"].append({
                    "action": "dataset_removed",
                    "details": f"Dataset '{session_id}' removed from project",
                    "timestamp": now,
                })
            return project.copy()

    def add_dashboard(self, project_id: str, dashboard_id: str, title: str) -> dict | None:
        with self._lock:
            project = self._store.get(project_id)
            if project is None:
                return None
            if dashboard_id in [d["dashboard_id"] for d in project["dashboards"]]:
                return project.copy()
            now = datetime.now(timezone.utc).isoformat()
            project["dashboards"].append({
                "dashboard_id": dashboard_id,
                "title": title,
                "added_at": now,
            })
            project["updated_at"] = now
            project["activity_log"].append({
                "action": "dashboard_added",
                "details": f"Dashboard '{title}' added to project",
                "timestamp": now,
            })
            return project.copy()

    def remove_dashboard(self, project_id: str, dashboard_id: str) -> dict | None:
        with self._lock:
            project = self._store.get(project_id)
            if project is None:
                return None
            original_count = len(project["dashboards"])
            project["dashboards"] = [d for d in project["dashboards"] if d["dashboard_id"] != dashboard_id]
            if len(project["dashboards"]) < original_count:
                now = datetime.now(timezone.utc).isoformat()
                project["updated_at"] = now
                project["activity_log"].append({
                    "action": "dashboard_removed",
                    "details": f"Dashboard '{dashboard_id}' removed from project",
                    "timestamp": now,
                })
            return project.copy()

    def get_activity(self, project_id: str, limit: int = 50) -> list[dict]:
        with self._lock:
            project = self._store.get(project_id)
            if project is None:
                return []
            log = project.get("activity_log", [])
            return log[-limit:][::-1]

    def add_activity(self, project_id: str, action: str, details: str) -> None:
        with self._lock:
            project = self._store.get(project_id)
            if project is None:
                return
            now = datetime.now(timezone.utc).isoformat()
            project["activity_log"].append({
                "action": action,
                "details": details,
                "timestamp": now,
            })
            project["updated_at"] = now


project_store = ProjectStore()
