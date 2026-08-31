# Assignment-to-file matching

## Candidate sources

Check in order:

1. Direct assignment attachment or file link in the description.
2. File/module item explicitly associated with the assignment.
3. Files adjacent to the assignment in the same module.
4. Course files matched by normalized title, assignment number, folder/week/topic, and metadata.

The CLI performs inexpensive lexical scoring first. Use model judgment only to break close ties from a small candidate list; do not send full course contents unnecessarily.

## Confidence

- 90–100: explicit or nearly certain association.
- 70–89: likely fuzzy match; disclose and ask before download when user did not already request likely related files.
- 50–69: present candidates and ask the user to choose.
- Below 50: do not associate automatically.

Always say when matching was fuzzy. Include candidate filename, confidence, and short reasons such as matching assignment number, title words, or same module. Never call a fuzzy result “the attached file”.

## Downloads

- Refresh the file object immediately before download because signed URLs can expire.
- Preserve the original extension and sanitize filenames. Avoid overwriting by adding the Canvas file ID.
- Report saved path, type, and size.
- After downloading, list all files and ask which to analyze. The user may choose individual files or all files.
