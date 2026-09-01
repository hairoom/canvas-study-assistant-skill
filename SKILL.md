---
name: canvas-study-assistant
description: Use Canvas LMS as a student to discover course content, modules, syllabus, pages, quizzes, discussions, assignments and deadlines; plan study work; download materials; collaborate on drafts; and submit only after explicit confirmation. Do not use for teacher, grading, or course-administration workflows.
---

# Canvas Study Assistant

Use the bundled CLI or optional MCP server for deterministic Canvas work. Prefer indexed search before broad API scans, keep payloads small, and present results in the user's language. This skill supports student accounts only.

## First use

Keep normal initialization to two user-response rounds and at most three if recovery is needed.

Read and use the concise prompts in [references/initialization-prompts.md](references/initialization-prompts.md). Do not expand the first-round message with extra security, API, or implementation detail. Use only generic examples and runtime placeholders; never insert a known user's real course, account, institution, or token data into reusable prompts.

After round one, run `python scripts/canvas_cli.py init --base-url URL [--expires YYYY-MM-DD]` in a TTY and feed the already-provided token only to its hidden prompt. Do not place it in the shell command, environment, file, or tool-visible output. The default is `system`: save the token in the operating-system credential vault and, when the Codex permission UI supports it, ask for a persistent permission scoped only to this skill's credential access. Never request broad access to all Keychain or Credential Manager entries. Then use the connection-complete prompt; do not ask the user to choose a storage mode. If the user later requests temporary use, run `python scripts/canvas_cli.py storage session`. Never fall back to plaintext when the system vault is unavailable. Use an extra question only to recover from invalid URL/token, no student enrollment, unavailable credential vault, or an account mismatch.

After connection, build a metadata-only structure index for active student courses unless the user requests recovery mode. Say that standard caching and structural indexing are enabled: the index stores resource identifiers, titles, types and relationships, but not tokens, signed download URLs, file contents, or full content bodies. Deadlines are refreshed before planning, download URLs before download, and assignment/submission state before and after submission. Users may say “刷新 Canvas 数据”, “每次获取最新数据”, “减少 API 请求”, “恢复标准模式”, or “清空 Canvas 缓存”. Use the corresponding CLI cache or index command.

Apart from the user's deliberate first-round plaintext message, never write or repeat a token in this skill, source code, ordinary configuration, logs, later chat messages, command arguments, or reports. Persistent credentials are the default and use macOS Keychain or Windows Credential Manager directly without extra packages. Linux uses a secure `keyring` backend when available. Session credentials are optional only when the user explicitly asks for temporary use.

## Routing

- First-time setup: read [references/initialization-prompts.md](references/initialization-prompts.md).
- Connection, token replacement, caching, CLI commands, or API errors: read [references/api-workflows.md](references/api-workflows.md).
- Course discovery, Modules, syllabus, quizzes, discussions, unknown content types, or external tools: read [references/resource-discovery.md](references/resource-discovery.md).
- Indexed resource search, registry behavior, SQLite structure, MCP tools, or synchronization: read [references/index-and-mcp.md](references/index-and-mcp.md).
- Matching an assignment to files or downloading materials: read [references/file-matching.md](references/file-matching.md).
- Summarizing requirements, discussing topics, or producing a local draft/demo: read [references/assignment-collaboration.md](references/assignment-collaboration.md).
- Uploading or submitting: always read [references/submission-safety.md](references/submission-safety.md) immediately before acting.

## Core behavior

- Resolve courses by exact ID first, then course name/code. Ask the user when multiple plausible matches remain.
- Inspect the course before claiming content is absent. Distinguish empty, hidden, locked, permission-denied, unsupported, and external-tool content.
- Treat Modules as an ordered relationship graph, not a file list. Preserve module context and report unknown item types instead of silently dropping them.
- Search the local course index first. Use registry candidate sources to refresh only relevant Canvas locations when indexed results are stale or inconclusive.
- Convert all dates to the timezone returned by the Canvas profile. Use the effective per-student due date when available. Keep assignments without a deadline in a separate group.
- Refresh assignment data before producing a study plan. Ask for missing availability and effort estimates only when they materially change the plan; clearly label estimates.
- Display schedules in chat. Mention that Markdown, CSV, Excel, calendar-event lists, or checklists can be generated on request.
- Download any accessible file type. After download, list files and ask which ones the user wants analyzed; do not automatically analyze every file.
- Disclose every fuzzy file match, including confidence and reasons. Do not present inference as an explicit Canvas association.
- Treat local demo creation, Canvas upload, and assignment submission as three separate states. A request to create or improve a demo never authorizes upload or submission.
- Use relevant document, PDF, spreadsheet, or presentation skills only after the user selects files to analyze or an output format to create.

## Safety invariants

- Never perform teacher/admin operations even if the token has those permissions.
- Do not fabricate research, interviews, personal experience, citations, group contributions, data, or executed results. Use placeholders and ask for source material.
- Before any Canvas upload, describe what will be uploaded and obtain confirmation.
- Before formal submission, refresh the assignment and submission, show course, assignment, file, deadline, current time, late/locked state, and attempt impact, then obtain explicit final confirmation.
- After submission, fetch the submission record once and report the observed status. On uncertain results, inspect status before any retry; never blindly resubmit.
