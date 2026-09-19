"""Application service shared by MCP and other structured frontends.

This layer turns low-level Canvas operations into compact student workflows.
The default backend is ``canvas_study.runtime``; tests can inject a fake
backend without credentials or network access.
"""

from __future__ import annotations

import mimetypes
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

from .service import CanvasStudyService
from .sync import sync_all


class CanvasApplication:
    """Structured Canvas workflows for MCP tools."""

    def __init__(self, backend: ModuleType | Any | None = None):
        if backend is None:
            from . import runtime as backend
        self.backend = backend

    def _connection(self):
        return self.backend.client()

    def _index_service(self) -> CanvasStudyService:
        return CanvasStudyService(self.backend.app_dir() / "resource-index.sqlite3")

    @staticmethod
    def _student_courses(items):
        return [
            course for course in items
            if any(
                enrollment.get("type") == "student"
                or enrollment.get("role") == "StudentEnrollment"
                for enrollment in course.get("enrollments", [])
            )
        ]

    def connection_status(self) -> dict[str, Any]:
        cfg = self.backend.config()
        if not cfg:
            return {"configured": False}
        try:
            self.backend.token_for(cfg)
            credential_available = True
        except RuntimeError:
            credential_available = False
        public = {
            key: cfg.get(key)
            for key in (
                "canvas_url", "canvas_user_id", "canvas_user_name", "timezone",
                "credential_mode", "token_expires_at", "cache_mode",
            )
        }
        return {"configured": True, "credential_available": credential_available, **public}

    def list_courses(self, refresh: bool = False) -> dict[str, Any]:
        api, cfg = self._connection()
        items = self._student_courses(self.backend.courses(api, cfg, refresh))
        return {
            "courses": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "course_code": item.get("course_code"),
                    "workflow_state": item.get("workflow_state"),
                }
                for item in items
            ]
        }

    def list_assignments(
        self, course: str, pending_only: bool = False, refresh: bool = False,
    ) -> dict[str, Any]:
        api, cfg = self._connection()
        selected = self.backend.course(api, cfg, course, refresh)
        items = self.backend.assignments(api, cfg, selected["id"], refresh)
        if pending_only:
            items = [
                item for item in items
                if (item.get("submission") or {}).get("workflow_state")
                not in {"submitted", "graded"}
            ]
        items.sort(key=lambda item: (item.get("due_at") is None, item.get("due_at") or ""))
        return {
            "course": {"id": selected["id"], "name": selected.get("name")},
            "timezone": cfg.get("timezone"),
            "assignments": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "due_at": item.get("due_at"),
                    "unlock_at": item.get("unlock_at"),
                    "lock_at": item.get("lock_at"),
                    "points": item.get("points_possible"),
                    "submission_types": item.get("submission_types"),
                    "description": self.backend.clean_html(item.get("description")),
                    "submission": item.get("submission"),
                }
                for item in items
            ],
        }

    def schedule(self, days: int = 7) -> dict[str, Any]:
        if not 1 <= days <= 365:
            raise ValueError("days must be between 1 and 365")
        api, cfg = self._connection()
        cutoff = datetime.now(timezone.utc) + timedelta(days=days)
        pending = []
        for course in self._student_courses(self.backend.courses(api, cfg, True)):
            for item in self.backend.assignments(api, cfg, course["id"], True):
                due_at = item.get("due_at")
                state = (item.get("submission") or {}).get("workflow_state")
                if not due_at or state in {"submitted", "graded"}:
                    continue
                try:
                    due = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if due <= cutoff:
                    pending.append({
                        "course": course.get("name"),
                        "course_id": course.get("id"),
                        "assignment": item.get("name"),
                        "assignment_id": item.get("id"),
                        "due_at": due_at,
                        "points": item.get("points_possible"),
                    })
        return {
            "timezone": cfg.get("timezone"),
            "days": days,
            "pending": sorted(pending, key=lambda item: item["due_at"]),
        }

    def get_modules(self, course: str, refresh: bool = False) -> dict[str, Any]:
        api, cfg = self._connection()
        selected = self.backend.course(api, cfg, course, refresh)
        return {
            "course": {"id": selected["id"], "name": selected.get("name")},
            "modules": self.backend.normalized_modules(api, cfg, selected["id"], refresh),
        }

    def get_files(self, course: str, refresh: bool = False) -> dict[str, Any]:
        api, cfg = self._connection()
        selected = self.backend.course(api, cfg, course, refresh)
        items = self.backend.course_files(api, cfg, selected["id"], refresh)
        return {
            "course": {"id": selected["id"], "name": selected.get("name")},
            "files": [
                {
                    "id": item.get("id"),
                    "name": item.get("display_name") or item.get("filename"),
                    "content_type": item.get("content-type"),
                    "size": item.get("size"),
                    "updated_at": item.get("updated_at"),
                    "module_contexts": item.get("module_contexts", []),
                }
                for item in items
            ],
        }

    def inspect_course(
        self, course: str, include_inventory: bool = False, refresh: bool = False,
    ) -> dict[str, Any]:
        api, cfg = self._connection()
        selected = self.backend.course(api, cfg, course, refresh)
        report = self.backend.discover_course(api, cfg, selected, refresh)
        for name, capability in report["capabilities"].items():
            if capability.get("status") != "available":
                continue
            data = capability.get("data") or []
            capability["count"] = len(data) if isinstance(data, list) else 1
            if name == "modules":
                capability["item_count"] = sum(len(module["items"]) for module in data)
            if not include_inventory:
                capability.pop("data", None)
        return report

    def sync_courses(self) -> dict[str, Any]:
        api, cfg = self._connection()
        items = self._student_courses(self.backend.courses(api, cfg, True))
        return sync_all(
            api, cfg, items, self.backend.discover_course,
            self.backend.app_dir() / "resource-index.sqlite3",
        )

    def find_resource(
        self, course_id: str, query: str, kinds: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        if not query.strip():
            raise ValueError("query must not be empty")
        return self._index_service().find_resource(
            course_id, query, kinds, min(max(limit, 1), 50),
        )

    def course_tree(self, course_id: str) -> dict[str, Any]:
        return self._index_service().course_tree(course_id)

    def sync_status(self) -> dict[str, Any]:
        return self._index_service().sync_status()

    def resource_registry(self) -> list[dict[str, Any]]:
        return self._index_service().registry()

    def match_assignment_files(self, course: str, assignment: str) -> dict[str, Any]:
        api, cfg = self._connection()
        selected_course = self.backend.course(api, cfg, course, True)
        selected_assignment = self.backend.assignment(
            api, cfg, selected_course["id"], assignment, True,
        )
        candidates = []
        for item in self.backend.course_files(api, cfg, selected_course["id"], True):
            score, reasons = self.backend.match_score(selected_assignment, item)
            if score >= 30:
                candidates.append({
                    "file_id": item.get("id"),
                    "name": item.get("display_name") or item.get("filename"),
                    "confidence": score,
                    "reasons": reasons,
                    "fuzzy_match": True,
                })
        return {
            "course": selected_course.get("name"),
            "assignment": selected_assignment.get("name"),
            "notice": "Canvas did not explicitly associate these candidates; results are fuzzy matches",
            "candidates": sorted(
                candidates, key=lambda item: item["confidence"], reverse=True,
            )[:10],
        }

    def download_file(self, file_id: str, output_directory: str) -> dict[str, Any]:
        api, _ = self._connection()
        file_info, _ = api.get(f"/api/v1/files/{file_id}")
        raw, _, _ = api.request("GET", file_info["url"])
        if not isinstance(raw, bytes):
            raise RuntimeError("Unexpected file response")
        folder = Path(output_directory).expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / self.backend.safe_name(
            file_info.get("display_name") or file_info.get("filename") or str(file_id)
        )
        if target.exists():
            target = target.with_name(f"{target.stem}-{file_id}{target.suffix}")
        target.write_bytes(raw)
        return {
            "downloaded": True,
            "file_id": file_info.get("id"),
            "name": target.name,
            "content_type": file_info.get("content-type"),
            "bytes": len(raw),
            "path": str(target),
        }

    def preview_upload(self, course: str, assignment: str, file_path: str) -> dict[str, Any]:
        api, cfg = self._connection()
        selected_course = self.backend.course(api, cfg, course, True)
        selected_assignment = self.backend.assignment(
            api, cfg, selected_course["id"], assignment, True,
        )
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise RuntimeError("Local file not found")
        return {
            "uploaded": False,
            "confirmation_required": f"UPLOAD:{selected_course['id']}:{selected_assignment['id']}",
            "course": selected_course.get("name"),
            "course_id": selected_course["id"],
            "assignment": selected_assignment.get("name"),
            "assignment_id": selected_assignment["id"],
            "file": str(path),
            "bytes": path.stat().st_size,
        }

    def upload_draft(
        self, course: str, assignment: str, file_path: str, confirmation: str,
    ) -> dict[str, Any]:
        preview = self.preview_upload(course, assignment, file_path)
        if confirmation != preview["confirmation_required"]:
            return preview
        api, _ = self._connection()
        path = Path(preview["file"])
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        initialized, _, _ = api.request(
            "POST",
            f"/api/v1/courses/{preview['course_id']}/assignments/{preview['assignment_id']}/submissions/self/files",
            [("name", path.name), ("size", str(path.stat().st_size)), ("content_type", content_type)],
        )
        uploaded = self.backend.upload_form(
            initialized["upload_url"], initialized.get("upload_params", {}), path,
        )
        return {
            "uploaded": True,
            "submitted": False,
            "file_id": uploaded.get("id"),
            "filename": uploaded.get("display_name") or uploaded.get("filename"),
        }

    @staticmethod
    def _submission(api, course_id, assignment_id):
        return api.get(
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self"
        )[0]

    def preview_submission(
        self, course: str, assignment: str, file_id: str,
    ) -> dict[str, Any]:
        api, cfg = self._connection()
        selected_course = self.backend.course(api, cfg, course, True)
        selected_assignment = self.backend.assignment(
            api, cfg, selected_course["id"], assignment, True,
        )
        current = self._submission(api, selected_course["id"], selected_assignment["id"])
        return {
            "course": selected_course.get("name"),
            "course_id": selected_course["id"],
            "assignment": selected_assignment.get("name"),
            "assignment_id": selected_assignment["id"],
            "file_id": file_id,
            "due_at": selected_assignment.get("due_at"),
            "unlock_at": selected_assignment.get("unlock_at"),
            "lock_at": selected_assignment.get("lock_at"),
            "timezone": cfg.get("timezone"),
            "current_submission": {
                key: current.get(key)
                for key in ("workflow_state", "submitted_at", "attempt", "late", "missing")
            },
            "confirmation_required": (
                f"SUBMIT:{selected_course['id']}:{selected_assignment['id']}:{file_id}"
            ),
        }

    def submit_assignment(
        self, course: str, assignment: str, file_id: str, confirmation: str,
    ) -> dict[str, Any]:
        preview = self.preview_submission(course, assignment, file_id)
        if confirmation != preview["confirmation_required"]:
            raise RuntimeError("Exact final confirmation required; run submission preview")
        api, _ = self._connection()
        before = self._submission(api, preview["course_id"], preview["assignment_id"])
        api.request(
            "POST",
            f"/api/v1/courses/{preview['course_id']}/assignments/{preview['assignment_id']}/submissions",
            [
                ("submission[submission_type]", "online_upload"),
                ("submission[file_ids][]", str(file_id)),
            ],
        )
        after = self._submission(api, preview["course_id"], preview["assignment_id"])
        return {
            "submitted": True,
            "previous_attempt": before.get("attempt"),
            "observed": {
                key: after.get(key)
                for key in (
                    "workflow_state", "submitted_at", "attempt", "late", "missing", "attachments",
                )
            },
        }
