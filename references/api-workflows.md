# API and credential workflows

## CLI

Run from the skill directory:

```text
python scripts/canvas_cli.py init --base-url https://canvas.example.edu --expires YYYY-MM-DD
python scripts/canvas_cli.py status
python scripts/canvas_cli.py update-token [--expires YYYY-MM-DD]
python scripts/canvas_cli.py storage session|system
python scripts/canvas_cli.py disconnect
python scripts/canvas_cli.py courses
python scripts/canvas_cli.py assignments --course COURSE --pending --refresh
python scripts/canvas_cli.py schedule --days 7
python scripts/canvas_cli.py files --course COURSE
python scripts/canvas_cli.py match-files --course COURSE --assignment ASSIGNMENT
python scripts/canvas_cli.py download --file-id FILE_ID --output DIRECTORY
python scripts/canvas_cli.py cache standard|realtime|low-request|clear
```

Commands emit JSON. Summarize useful fields; do not paste large raw payloads unless requested.

The CLI normally uses the platform's application-data directory for non-secret configuration and cache. If the Codex filesystem sandbox does not allow that directory, request access to that single app directory or set `CANVAS_ASSISTANT_HOME` to a user-approved writable directory. Tokens are never stored there.

## Credential rules

- On first use, the user may provide the token as plaintext in the conversation after being told it will remain visible in chat history. Never repeat or quote it. Feed it only into the CLI's hidden prompt; do not put it in command arguments, environment variables, files, or output.
- If the user prefers, use the hidden local prompt without placing the token in chat. `init` and `update-token` always consume tokens through `getpass` at the CLI boundary.
- Default storage is `system`: macOS Keychain or Windows Credential Manager directly, with no extra package. On Linux it uses a secure Python `keyring` backend when available. If no secure system vault is available, explain the limitation and ask before switching to session mode; never store a persistent token in config.
- When the Codex permission UI supports persistent approval, recommend “始终允许” only for this skill's narrowly scoped credential read. Never request broad permission to read all system credentials.
- Session mode is optional and used only when the user explicitly asks for “仅本次使用”. It stores an expiring token in the current user's OS temporary directory; on POSIX the file is mode `0600`.
- Update tokens atomically: validate the new token first. If the Canvas user ID differs, report an account switch and require user confirmation before replacement.
- A `401` likely means an expired/revoked token. Offer token update. Retry a failed read once after update; never automatically retry an upload or submission.

## Cache modes

Standard is the default and is not asked during initialization.

- `standard`: profile 24h, courses 30m, assignments 5m, planner/todo 2m, files/modules 15m.
- `realtime`: minimal caching; explain that results are fresher but queries may be slower.
- `low-request`: longer caching; explain that recent changes may appear later.

Regardless of mode, force refresh before planning, downloads, uploads, and submissions. Never persist signed download URLs. Cache contains no tokens. Disconnect removes credentials and cache but not downloaded user files.

## Course and assignment interpretation

- Student scope only: accept active `StudentEnrollment`; ignore elevated capabilities.
- Follow Canvas `Link` headers for pagination.
- Treat `due_at=null` as no deadline, not as completed.
- Prefer assignment data returned for the current user and date overrides.
- Convert ISO timestamps to the profile timezone.
- A `403` is permission denial. A `404` may mean absent or hidden content. Do not claim a new token will fix either.
