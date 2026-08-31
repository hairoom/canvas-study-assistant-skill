# Course resource discovery

## Discovery workflow

Run `inspect-course --course COURSE` before concluding that content is absent. Use `--full` only when the user needs the actual inventory; the default returns counts and capability states to keep payloads small. Use `doctor` when diagnosing an institution- or account-specific failure.

Discovery covers the syllabus, visible navigation tabs, Modules and Module Items, course Files, Pages, Assignments, Discussions, Announcements, Classic Quizzes, New Quizzes, and visible course-navigation external tools. Availability varies by institution, course settings, enrollment overrides, release conditions, token scopes, and Canvas version.

## Modules

Request Modules with `include[]=items` and `include[]=content_details`, but never assume Canvas will inline every item. When `items` is absent, fetch that module's paginated items endpoint. Preserve order, prerequisites, sequential-progress rules, per-user state, lock details, `raw_type`, and `content_id`.

Known item types are File, Page, Assignment, Quiz, Discussion, ExternalUrl, ExternalTool, and SubHeader. Return unknown types as `kind=unknown` with `supported=false`; do not discard them. Resolve File items through `/api/v1/files/{content_id}` even when they are absent from the course Files endpoint.

## Capability states

- `available`: the endpoint returned successfully; an empty list means available but empty.
- `permission_denied`: Canvas returned 403.
- `hidden_or_missing`: Canvas returned 404; the object may be hidden or absent.
- `unauthorized`: the credential is invalid, expired, revoked, or out of scope.
- `rate_limited`: Canvas returned 429; stop broad discovery and retry later rather than looping.
- `unsupported_or_unavailable`: the CLI or Canvas instance could not provide the capability for another explicit reason.

Never convert these states into an empty list or claim that replacing a token will fix a 403/404.

## Quizzes and external tools

Classic Quizzes and New Quizzes use different API families. Report their capability states separately. A course may expose New Quizzes through assignments or LTI while denying direct quiz API access.

External tools can be discovered as Canvas navigation or Module items, but their internal content may live with a third-party LTI provider and require a separate authenticated launch. Report `external_tool` or `external_url` honestly; do not claim the Canvas token can read third-party content.

## Read-only fallback

Use `api-get` only for a same-origin path beginning with `/api/`. It accepts GET parameters, optional pagination, and a result limit. Credentials in paths or parameters are forbidden. Prefer a dedicated command whenever one exists, especially for uploads and submissions.
