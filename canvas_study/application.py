"""Application service shared by MCP and other structured frontends.

This layer turns low-level Canvas operations into compact student workflows.
The default backend is ``canvas_study.runtime``; tests can inject a fake
backend without credentials or network access.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlparse

from .index import ResourceIndex, normalize
from .service import CanvasStudyService
from .sync import ingest_course_report, item_key, sync_all


OFFICIAL_CANVAS_DOCS = "https://developerdocs.instructure.com/services/canvas"


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
    def _scrub(value):
        if isinstance(value, list):
            return [CanvasApplication._scrub(item) for item in value]
        if not isinstance(value, dict):
            return value
        blocked = {"access_token", "authorization", "token"}
        return {
            key: CanvasApplication._scrub(item)
            for key, item in value.items() if key.casefold() not in blocked
        }

    @staticmethod
    def _safe_api_request(path: str, params: dict[str, str] | None) -> tuple[str, list[tuple[str, str]]]:
        path = path.strip()
        if not path.startswith("/api/") or path.startswith("//") or urlparse(path).netloc:
            raise RuntimeError("Discovery accepts only same-origin paths beginning with /api/")
        if re.search(r"(?:access_token|authorization|token)=", path, re.I):
            raise RuntimeError("Credentials are forbidden in discovery paths")
        fields = []
        for key, value in (params or {}).items():
            if key.casefold() in {"access_token", "authorization", "token"}:
                raise RuntimeError("Credential parameters are forbidden")
            if len(key) > 100 or len(str(value)) > 500:
                raise RuntimeError("Discovery parameter is too large")
            fields.append((key, str(value)))
        if len(fields) > 20:
            raise RuntimeError("Discovery accepts at most 20 parameters")
        return path, fields

    def _read_api(self, api, path, params=None, paginate=False, limit=100):
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        path, fields = self._safe_api_request(path, params)
        value = api.pages(path, fields, limit=limit) if paginate else api.get(path, fields)[0]
        return self._scrub(value)

    @staticmethod
    def _payload_items(payload, items_field: str | None):
        if items_field:
            if not re.fullmatch(r"[A-Za-z0-9_]+", items_field):
                raise RuntimeError("items_field must be one top-level JSON field")
            if not isinstance(payload, dict) or not isinstance(payload.get(items_field), list):
                raise RuntimeError(f"Discovery response has no list field '{items_field}'")
            return payload[items_field]
        if not isinstance(payload, list):
            raise RuntimeError("Discovery response must be a list or use items_field")
        return payload

    @staticmethod
    def _title_score(query: str, title: str) -> int:
        query_norm, title_norm = normalize(query), normalize(title)
        if not query_norm or not title_norm:
            return 0
        if query_norm == title_norm:
            return 100
        if query_norm in title_norm:
            return 80
        query_tokens, title_tokens = set(query_norm.split()), set(title_norm.split())
        overlap = len(query_tokens & title_tokens) / max(1, len(query_tokens))
        similarity = SequenceMatcher(None, query_norm, title_norm).ratio()
        return round(max(overlap * 70, similarity * 60))

    @staticmethod
    def _index_api_items(index, course, kind, rows, id_field, title_field, source, metadata=None):
        indexed = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            identifier, title = row.get(id_field), row.get(title_field)
            if identifier is None or not isinstance(title, str) or not title.strip():
                continue
            index.upsert_resource({
                "resource_key": item_key(course["id"], kind, identifier),
                "course_id": course["id"], "kind": kind, "canvas_id": identifier,
                "lookup_id": identifier, "title": title.strip(), "status": "available",
                "source": source, "metadata": metadata or {},
            })
            indexed.append({"id": str(identifier), "title": title.strip(), "kind": kind})
        return indexed

    @staticmethod
    def _discovery_clues(report):
        clues = []
        modules = ((report.get("capabilities") or {}).get("modules") or {}).get("data") or []
        for module in modules:
            for item in module.get("items", []):
                if item.get("kind") in {"unknown", "external_tool", "external_url"}:
                    clues.append({
                        key: item.get(key) for key in (
                            "kind", "raw_type", "title", "content_id", "html_url",
                            "external_url", "module_id", "module_name",
                        ) if item.get(key) is not None
                    })
        return clues[:20]

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
        limit = min(max(limit, 1), 50)
        service = self._index_service()
        initial = service.find_resource(course_id, query, kinds, limit)
        if initial["results"] and initial["results"][0]["confidence"] >= 50:
            return {**initial, "search_mode": "index", "automatic_discovery": False}

        try:
            api, cfg = self._connection()
            selected = self.backend.course(api, cfg, str(course_id), True)
            report = self.backend.discover_course(api, cfg, selected, True)
            index = ResourceIndex(self.backend.app_dir() / "resource-index.sqlite3")
            try:
                ingest_course_report(index, report)
                host = urlparse(cfg["canvas_url"]).netloc.casefold()
                source_errors = []
                for source in index.discovery_sources(host, str(selected["id"])):
                    try:
                        payload = self._read_api(
                            api, source["path"], source["params"], source["paginate"], 200,
                        )
                        rows = self._payload_items(payload, source.get("items_field"))
                        self._index_api_items(
                            index, selected, source["kind"], rows, source["id_field"],
                            source["title_field"], "learned_endpoint",
                            {"discovery_source": source["source_key"]},
                        )
                    except (RuntimeError, ValueError) as exc:
                        source_errors.append({"source_key": source["source_key"], "error": str(exc)[:200]})
                index.commit()
            finally:
                index.close()
            refreshed = service.find_resource(str(selected["id"]), query, kinds, limit)
        except (RuntimeError, OSError, KeyError, ValueError) as exc:
            return {
                **initial,
                "search_mode": "index",
                "automatic_discovery": True,
                "discovery": {"status": "refresh_failed", "detail": str(exc)},
            }

        if refreshed["results"] and refreshed["results"][0]["confidence"] >= 50:
            return {
                **refreshed,
                "search_mode": "automatic_refresh",
                "automatic_discovery": True,
                "discovery": {"status": "resolved_from_refreshed_sources"},
            }
        return {
            **refreshed,
            "search_mode": "dynamic_discovery",
            "automatic_discovery": True,
            "discovery": {
                "status": "endpoint_research_required",
                "trigger": "no_reliable_result_after_index_and_live_refresh",
                "official_docs": OFFICIAL_CANVAS_DOCS,
                "candidate_sources": refreshed.get("candidate_sources", []),
                "clues": self._discovery_clues(report),
                "learned_source_errors": source_errors,
                "next_action": (
                    "Search official Canvas documentation using these clues, then validate a candidate "
                    "with canvas_discover_api_resources. Do not ask the user to assert that the resource exists."
                ),
            },
        }

    def read_api(
        self, path: str, params: dict[str, str] | None = None,
        paginate: bool = False, limit: int = 100,
    ) -> dict[str, Any]:
        """Read one bounded same-origin Canvas API path without persisting a rule."""
        api, _ = self._connection()
        return {"path": path, "data": self._read_api(api, path, params, paginate, limit)}

    def discover_api_resources(
        self, course: str, query: str, kind: str, path: str,
        id_field: str = "id", title_field: str = "title",
        items_field: str | None = None, params: dict[str, str] | None = None,
        paginate: bool = True, evidence: str = OFFICIAL_CANVAS_DOCS,
    ) -> dict[str, Any]:
        """Verify a read-only endpoint and persist only query-relevant resources and its rule."""
        if not query.strip():
            raise ValueError("query must not be empty")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", kind):
            raise ValueError("kind must be a lowercase resource identifier")
        for field in (id_field, title_field):
            if not re.fullmatch(r"[A-Za-z0-9_]+", field):
                raise ValueError("id_field and title_field must be top-level JSON fields")
        if not evidence.strip() or len(evidence) > 1000:
            raise ValueError("evidence must briefly identify the official documentation or live clue")
        evidence = evidence.strip()
        evidence_url = urlparse(evidence)
        if evidence_url.scheme:
            if evidence_url.scheme != "https" or evidence_url.netloc.casefold() != "developerdocs.instructure.com":
                raise RuntimeError("Documentation evidence must use the official Instructure developer domain")
        elif not evidence.startswith("live_canvas_clue:"):
            raise RuntimeError("Non-documentation evidence must start with live_canvas_clue:")

        api, cfg = self._connection()
        selected = self.backend.course(api, cfg, course, True)
        course_marker = f"/courses/{selected['id']}/"
        context_marker = f"course_{selected['id']}"
        if course_marker not in urlparse(path).path and context_marker not in (params or {}).values():
            raise RuntimeError("Learned discovery endpoints must be scoped to the selected course")
        payload = self._read_api(api, path, params, paginate, 200)
        rows = self._payload_items(payload, items_field)
        candidates = [
            row for row in rows
            if isinstance(row, dict)
            and row.get(id_field) is not None
            and isinstance(row.get(title_field), str)
            and self._title_score(query, row[title_field]) >= 35
        ]
        if not candidates:
            raise RuntimeError("The candidate endpoint returned no resource relevant to the query")

        host = urlparse(cfg["canvas_url"]).netloc.casefold()
        rule_value = {
            "canvas_host": host, "course_id": str(selected["id"]), "kind": kind,
            "path": path, "params": params or {}, "paginate": paginate,
            "items_field": items_field, "id_field": id_field, "title_field": title_field,
        }
        source_key = "discovery:" + hashlib.sha256(
            json.dumps(rule_value, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:20]
        index = ResourceIndex(self.backend.app_dir() / "resource-index.sqlite3")
        try:
            index.upsert_course(selected)
            indexed = self._index_api_items(
                index, selected, kind, candidates, id_field, title_field,
                "learned_endpoint", {"discovery_source": source_key},
            )
            index.upsert_discovery_source({
                **rule_value, "source_key": source_key, "evidence": evidence,
                "status": "verified",
            })
            index.commit()
        finally:
            index.close()
        return {
            "verified": True, "source_key": source_key, "course_id": str(selected["id"]),
            "kind": kind, "indexed": indexed, "evidence": evidence,
            "scope": "local_canvas_host_and_course",
        }

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
