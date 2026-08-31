# Upload and submission safety

## Separate states

1. Local demo: no Canvas mutation.
2. Staged upload: file exists in Canvas but the assignment is not submitted.
3. Formal submission: Canvas records a submission attempt.

Never collapse these states in language or implementation.

## Upload

Before `upload-draft`, show course, assignment, local filename, size, and purpose. Ask for confirmation. Upload once and retain the returned Canvas file ID. If the result is uncertain, inspect files/submission state rather than uploading again blindly.

## Submission

Immediately before submission, force-refresh assignment and current submission. Show course and assignment, staged filename/file ID, effective deadline in the user's timezone, current time, open/locked/late state, and existing attempt/status.

Ask “确认现在正式提交到 Canvas 吗？” Only a clear response to this final summary authorizes submission. Earlier approval to create, download, analyze, or upload does not.

Use `submission-preview` to obtain the exact confirmation phrase, then call `submit` only after confirmation. Afterward fetch the submission record and report `workflow_state`, `submitted_at`, `attempt`, `late`, and attachments. On network ambiguity, query status before considering a retry.
