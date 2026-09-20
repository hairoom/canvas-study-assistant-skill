# Resource index and MCP

## Components

- `canvas_study/runtime.py` owns Canvas HTTP, credentials, caching, resource discovery, and low-level transfer operations.
- `canvas_study/application.py` is the shared workflow layer used by MCP and the CLI fallback.
- `canvas_study/registry.py` is the structured API capability knowledge base. Each resource kind records user-language aliases, likely Canvas locations, and list/detail endpoints.
- `canvas_study/sync.py` converts course discovery reports into metadata-only resources and relationships.
- `canvas_study/index.py` stores courses, resources, relations, and capability states in SQLite and performs compact lexical/context ranking.
- `canvas_study/service.py` provides the index/search service used by the application layer.
- `mcp_server/server.py` is the primary structured Agent interface.
- `scripts/canvas_cli.py` is a thin bootstrap, recovery, and developer wrapper over the same runtime/application.

## Search workflow

Use `canvas_find_resource` first, or `find-resource` only as a fallback. It corrects close spelling errors, searches the index, automatically performs a live single-course structural refresh when no result reaches the reliability threshold, refreshes verified learned sources, and searches again. The registry reports candidate locations such as Module Items, course Files, syllabus links, Pages, and Assignment attachments. Results include confidence, reasons, and related Module/context nodes. Explicit Canvas relationships outrank fuzzy title inference.

If no reliable result exists after automatic refresh, the response enters `dynamic_discovery` and supplies compact unknown/external Module clues plus the official documentation root. The Agent may research a candidate endpoint without asking the user to assert that the resource exists. Only `canvas_discover_api_resources` may persist a learned source: it must be a verified, same-origin, course-scoped GET response containing a query-relevant resource. Detail bodies and files remain on-demand; do not turn discovery into a full-content crawl.

## Index safety

The SQLite index may store resource IDs, titles, types, timestamps, lock states, small metadata fields, graph relationships, and verified local discovery rules. Learned rules are scoped by Canvas host and course and include only endpoint paths, non-secret parameters, field mappings, evidence, and verification time. Never store access tokens, authorization headers, signed URLs, file bytes, full Page/Assignment/Discussion bodies, or submission content in the structural index.

## MCP

The MCP server uses the official Python MCP SDK v2 listed in `requirements-mcp.txt`. It is the normal Agent-facing interface and calls the shared application service directly; it never shells out to the CLI. The CLI remains available when MCP is unavailable and for local setup or diagnosis.

Available tools:

- `canvas_get_connection_status`: configuration and credential availability without secrets.
- `canvas_list_courses`: active student courses.
- `canvas_list_assignments`: course assignments, deadlines, and submission state.
- `canvas_get_schedule`: pending assignments in a bounded date window.
- `canvas_find_resource`: cross-source exact/fuzzy resource lookup.
- `canvas_read_api`: bounded same-origin GET probe for dynamic discovery.
- `canvas_discover_api_resources`: verify a course-scoped GET endpoint, index matching resources, and save its local rule.
- `canvas_get_course_tree`: indexed Module/resource structure.
- `canvas_get_modules`, `canvas_get_files`, `canvas_inspect_course`: live course discovery.
- `canvas_get_sync_status`: coverage and capability states.
- `canvas_get_resource_registry`: supported kinds, aliases, sources, and endpoints.
- `canvas_sync_courses`: metadata-only refresh for active student courses.
- `canvas_match_assignment_files`: disclosed fuzzy file candidates after refresh.
- `canvas_download_file`: one user-selected file with observed path and size.
- `canvas_preview_upload`, `canvas_upload_draft`: separate preview and upload steps.
- `canvas_preview_submission`, `canvas_submit_assignment`: separate final preview and submission steps.

Never call an upload or submission execution tool until the matching preview has been shown and the user has explicitly confirmed it. These dedicated tools keep writes out of the generic registry and read-only discovery paths.
