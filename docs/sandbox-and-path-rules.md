# Sandbox And Path Rules

All workflow activity must happen inside the Codex sandbox or an explicitly approved repo workspace.

## Rules

- All work happens in the Codex sandbox or approved repo workspace.
- Original Word documents must be copied before review.
- Never overwrite user-provided files.
- Outputs must go into an explicit output folder.
- Subagents should use relative paths from the approved workspace where possible.
- If absolute paths are used, they must be confirmed by the Orchestrator.
- Do not follow symlinks outside the workspace.
- Do not delete folders except workflow-created temporary output folders.
- If a path is ambiguous, stop and ask the user.

## Word Document Handling

The original Word document is an immutable source artifact. The workflow may read it, map it, and copy it, but must not modify it.

Any reviewed document must be created as a separate working copy before document application begins. Reviewer subagents must not write to either the original or the working copy.

## Recommended Workspace Layout

```text
qa_run/
  input/
    original.docx
  working/
    reviewed-copy.docx
    document-map.json
  outputs/
    reviewed.docx
    issue-log.md
    issue-log.csv
    audit-report.md
    unresolved-issues.md
```

## Output Placement

Use `qa_run/outputs/` for final user-facing outputs:

- reviewed `.docx`
- issue log `.md`
- issue log `.csv`
- audit report `.md`
- unresolved issues note `.md`

Use `qa_run/working/` for intermediate workflow artifacts:

- reviewed working copy before final output
- document map
- application log
- temporary issue-log versions

## Ambiguity Handling

If any input, working, or output path is unclear, conflicting, outside the approved workspace, or could overwrite a user-provided file, stop and ask the user before continuing.

