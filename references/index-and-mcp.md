# Resource index and MCP

## Components

- `canvas_study/registry.py` is the structured API capability knowledge base. Each resource kind records user-language aliases, likely Canvas locations, and list/detail endpoints.
- `canvas_study/sync.py` converts course discovery reports into metadata-only resources and relationships.
- `canvas_study/index.py` stores courses, resources, relations, and capability states in SQLite and performs compact lexical/context ranking.
- `canvas_study/service.py` is the shared high-level API used by both CLI and MCP.
- `mcp_server/server.py` exposes narrow tools so an agent can search a persistent index without receiving the entire course tree.

## Search workflow

Use `find-resource` or `canvas_find_resource` first. The registry infers likely resource kinds and reports candidate locations such as Module Items, course Files, syllabus links, Pages, and Assignment attachments. Results include confidence, reasons, and related Module/context nodes. Explicit Canvas relationships outrank fuzzy title inference.

If no reliable indexed result exists, refresh the course structure and retry. Detail bodies and files remain on-demand; do not turn a metadata search into a full-content crawl.

## Index safety

The SQLite index may store resource IDs, titles, types, timestamps, lock states, small metadata fields, and graph relationships. Never store access tokens, authorization headers, signed URLs, file bytes, full Page/Assignment/Discussion bodies, or submission content in the structural index.

## MCP

The MCP server is optional and requires the official Python `mcp` package listed in `requirements-mcp.txt`. It does not replace Canvas API access. It keeps search and sync tools structured and compact while reusing the same Python core as the CLI.

Available tools:

- `canvas_find_resource`: cross-source exact/fuzzy resource lookup.
- `canvas_get_course_tree`: indexed Module/resource structure.
- `canvas_get_sync_status`: coverage and capability states.
- `canvas_get_resource_registry`: supported kinds, aliases, sources, and endpoints.
- `canvas_sync_courses`: metadata-only refresh for active student courses.

Uploads and submissions remain dedicated CLI safety workflows; do not expose them through a generic registry or generic write tool.
