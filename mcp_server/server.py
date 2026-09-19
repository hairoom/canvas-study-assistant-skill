#!/usr/bin/env python3
"""Primary structured Agent interface for Canvas Study Assistant.

Install the official Python MCP SDK to run this server: ``pip install mcp``.
The developer CLI and MCP server share ``CanvasApplication`` and one runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from mcp.server import MCPServer
except ImportError as exc:
    raise SystemExit("The MCP server requires the official 'mcp' Python package") from exc

from canvas_study.application import CanvasApplication


mcp = MCPServer("Canvas Study Assistant")


def application(): return CanvasApplication()


@mcp.tool()
def canvas_get_connection_status() -> dict:
    """Report configuration and credential availability without exposing secrets."""
    return application().connection_status()


@mcp.tool()
def canvas_list_courses(refresh: bool = False) -> dict:
    """List active courses where the current account is enrolled as a student."""
    return application().list_courses(refresh)


@mcp.tool()
def canvas_list_assignments(
    course: str, pending_only: bool = False, refresh: bool = False,
) -> dict:
    """List assignments for one course with deadlines and current submission state."""
    return application().list_assignments(course, pending_only, refresh)


@mcp.tool()
def canvas_get_schedule(days: int = 7) -> dict:
    """Return pending assignments due within a bounded number of days."""
    return application().schedule(days)


@mcp.tool()
def canvas_find_resource(course_id: str, query: str, kinds: list[str] | None = None, limit: int = 10) -> dict:
    """Find course resources using exact title, fuzzy terms, and module context."""
    return application().find_resource(course_id, query, kinds, limit)


@mcp.tool()
def canvas_get_course_tree(course_id: str) -> dict:
    """Return the indexed module/resource structure without fetching full content."""
    return application().course_tree(course_id)


@mcp.tool()
def canvas_get_modules(course: str, refresh: bool = False) -> dict:
    """Return ordered modules and normalized module items for one course."""
    return application().get_modules(course, refresh)


@mcp.tool()
def canvas_get_files(course: str, refresh: bool = False) -> dict:
    """Return course files merged with their module context."""
    return application().get_files(course, refresh)


@mcp.tool()
def canvas_inspect_course(
    course: str, include_inventory: bool = False, refresh: bool = False,
) -> dict:
    """Inspect content capabilities; include inventories only when specifically needed."""
    return application().inspect_course(course, include_inventory, refresh)


@mcp.tool()
def canvas_get_sync_status() -> dict:
    """Report indexed course/resource counts and per-capability sync states."""
    return application().sync_status()


@mcp.tool()
def canvas_get_resource_registry() -> list[dict]:
    """List resource kinds, aliases, candidate locations, and Canvas endpoints."""
    return application().resource_registry()


@mcp.tool()
def canvas_sync_courses() -> dict:
    """Refresh structural metadata for all active student courses; no file downloads or content-body crawl."""
    return application().sync_courses()


@mcp.tool()
def canvas_match_assignment_files(course: str, assignment: str) -> dict:
    """Return disclosed fuzzy file candidates for an assignment after live refresh."""
    return application().match_assignment_files(course, assignment)


@mcp.tool()
def canvas_download_file(file_id: str, output_directory: str) -> dict:
    """Download one selected Canvas file and return its actual local path and size."""
    return application().download_file(file_id, output_directory)


@mcp.tool()
def canvas_preview_upload(course: str, assignment: str, file_path: str) -> dict:
    """Refresh the target and return an upload preview; this tool does not upload."""
    return application().preview_upload(course, assignment, file_path)


@mcp.tool()
def canvas_upload_draft(
    course: str, assignment: str, file_path: str, confirmation: str,
) -> dict:
    """Upload one reviewed file without submitting; call only after explicit user confirmation."""
    return application().upload_draft(course, assignment, file_path, confirmation)


@mcp.tool()
def canvas_preview_submission(course: str, assignment: str, file_id: str) -> dict:
    """Refresh assignment/submission state and return a final submission preview."""
    return application().preview_submission(course, assignment, file_id)


@mcp.tool()
def canvas_submit_assignment(
    course: str, assignment: str, file_id: str, confirmation: str,
) -> dict:
    """Submit one uploaded file; call only after explicit confirmation of the fresh preview."""
    return application().submit_assignment(course, assignment, file_id, confirmation)


if __name__ == "__main__": mcp.run()
