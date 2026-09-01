#!/usr/bin/env python3
"""Optional MCP facade over the shared Canvas index.

Install the official Python MCP SDK to run this server: ``pip install mcp``.
The Canvas core and CLI remain dependency-free.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit("The optional MCP server requires the official 'mcp' Python package") from exc

import canvas_cli
from canvas_study.service import CanvasStudyService
from canvas_study.sync import sync_all


mcp = FastMCP("Canvas Study Assistant")


def service(): return CanvasStudyService(canvas_cli.app_dir() / "resource-index.sqlite3")


@mcp.tool()
def canvas_find_resource(course_id: str, query: str, kinds: list[str] | None = None, limit: int = 10) -> dict:
    """Find course resources using exact title, fuzzy terms, and module context."""
    return service().find_resource(course_id, query, kinds, min(max(limit, 1), 50))


@mcp.tool()
def canvas_get_course_tree(course_id: str) -> dict:
    """Return the indexed module/resource structure without fetching full content."""
    return service().course_tree(course_id)


@mcp.tool()
def canvas_get_sync_status() -> dict:
    """Report indexed course/resource counts and per-capability sync states."""
    return service().sync_status()


@mcp.tool()
def canvas_get_resource_registry() -> list[dict]:
    """List resource kinds, aliases, candidate locations, and Canvas endpoints."""
    return service().registry()


@mcp.tool()
def canvas_sync_courses() -> dict:
    """Refresh structural metadata for all active student courses; no file downloads or content-body crawl."""
    api, cfg = canvas_cli.client()
    student_courses = [c for c in canvas_cli.courses(api, cfg, True) if any(
        e.get("type") == "student" or e.get("role") == "StudentEnrollment" for e in c.get("enrollments", []))]
    return sync_all(api, cfg, student_courses, canvas_cli.discover_course, canvas_cli.app_dir() / "resource-index.sqlite3")


if __name__ == "__main__": mcp.run()
