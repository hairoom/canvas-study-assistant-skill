# Upload and submission safety

## Separate states

1. Local demo: no Canvas mutation.
2. Staged upload: file exists in Canvas but the assignment is not submitted.
3. Formal submission: Canvas records a submission attempt.

Never collapse these states in language or implementation.

## Upload

Call `canvas_preview_upload` (or the CLI fallback) and show course, assignment, local filename, size, and purpose. Ask for confirmation, then call `canvas_upload_draft` with the returned confirmation value. Upload once and retain the returned Canvas file ID. If the result is uncertain, inspect files/submission state rather than uploading again blindly.

## Submission

Immediately before submission, force-refresh assignment and current submission. Show course and assignment, staged filename/file ID, effective deadline in the user's timezone, current time, open/locked/late state, and existing attempt/status.

Ask “确认现在正式提交到 Canvas 吗？” Only a clear response to this final summary authorizes submission. Earlier approval to create, download, analyze, or upload does not.

Use `canvas_preview_submission` (or `submission-preview`) to obtain the exact confirmation phrase, then call `canvas_submit_assignment` (or `submit`) only after confirmation. Afterward report the freshly fetched `workflow_state`, `submitted_at`, `attempt`, `late`, and attachments. On network ambiguity, query status before considering a retry.
