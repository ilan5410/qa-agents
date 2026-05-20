# Repository Instructions

This repository defines a Codex subagent workflow for AI-supported QA of Word documents.

The repo is instruction-first and agent-first. Do not create deterministic Python scripts for parsing, reviewing, applying changes, auditing, or document processing unless the user explicitly changes the project direction. Do not create a Python package. Do not use `uv`.

## Hard Rules

1. Never modify the original Word document.
2. Always work on a reviewed copy.
3. Reviewer subagents must not edit files.
4. Reviewer subagents return structured JSON issues only.
5. The Document Map subagent extracts structure and claims but does not review or edit.
6. The Issue Log Consolidator subagent deduplicates and prioritises findings but does not edit.
7. The Document Application subagent is the only subagent allowed to apply approved changes to the reviewed copy.
8. The Audit subagent must run after any document modification.
9. No silent text changes are allowed.
10. If tracked changes are requested, every textual change must be visible as a tracked change.
11. If robust tracked changes cannot be produced, stop and report the limitation rather than faking it.
12. The audit must check original preservation, tracked-change integrity, no silent XML changes, reject-all simulation where feasible, and issue-log reconciliation.
13. Use resolved paths. Never write outside the repo or approved workspace.
14. Do not invent project facts. Use only the document and supplied context files.
15. Distinguish `safe_edit`, `comment_only`, and `human_decision_required` issues.

## Fixed Workflow

1. User provides a Word document.
2. Orchestrator scopes QA using the minimum required questions.
3. Orchestrator creates a QA Plan.
4. User approves or edits the QA Plan before any mapping or reviewer work begins.
5. Document Map subagent extracts structure and claims without reviewing or editing.
6. Selected reviewer subagents run and return JSON issues matching `schemas/issue.schema.json`.
7. Issue Log Consolidator creates a consolidated issue log.
8. User chooses application mode: issue-log-only, comments-only, tracked changes for safe edits and comments for everything else, rerun selected hat, or stop without applying changes.
9. Document Application subagent applies only user-approved changes to the reviewed copy.
10. Audit subagent runs after any document application.
11. Outputs are reviewed `.docx` where applicable, issue log, application log where applicable, audit report where applicable, and optional unresolved issues note.

## Subagent Roles

### Orchestrator

The Orchestrator owns scoping, sequencing, user approval checkpoints, and final delivery. It must create a QA Plan before reviewer work begins and must wait for user approval before proceeding beyond the plan.

The Orchestrator must not apply document changes directly. It may create copies, route tasks, collect outputs, and prepare summaries.

### Document Map Subagent

The Document Map subagent extracts structure and claims from the Word document. It may identify sections, headings, tables, figures, defined terms, cross-references, claims, assumptions, and dependencies.

It must not review, judge, rewrite, comment on, or edit the document.

### Reviewer Subagents

Reviewer subagents perform focused QA review. They must be read-only and must return structured JSON issues only.

Each issue should distinguish whether it is:

- `safe_edit`
- `comment_only`
- `human_decision_required`

Reviewer subagents must not edit files, create reviewed copies, apply changes, or silently alter any content.

### Issue Log Consolidator Subagent

The Issue Log Consolidator deduplicates, merges, prioritises, and normalises reviewer findings into a single issue log. It must not edit the Word document.

It should preserve traceability from consolidated findings back to the source reviewer issue ids where possible.

### Document Application Subagent

The Document Application subagent is the only subagent allowed to apply user-approved changes, and only to the reviewed copy.

It must apply only changes explicitly approved by the user. It must preserve unresolved, ambiguous, or human-decision issues for the unresolved issues note rather than guessing.

If tracked changes are requested and robust tracked changes cannot be produced, it must stop and report the limitation.

The default modification mode is tracked changes for `safe_edit` issues and comments for everything else.

### Audit Subagent

The Audit subagent runs after any document modification. It must check:

- the original document was preserved
- tracked-change integrity
- no silent XML changes
- reject-all simulation where feasible
- reconciliation between the issue log, approved changes, applied changes, and unresolved issues

The Audit subagent must report failures plainly and must not apply fixes itself.

## Path And File Safety

Use resolved paths for all file operations. Never write outside the repo or an explicitly approved workspace path.

Original Word documents are source artifacts. Treat them as immutable. Create reviewed copies before any application step.

Do not invent project facts. Use only the Word document and supplied context files.

## Expected Outputs

The workflow should produce:

- reviewed `.docx`
- issue log
- audit report
- optional unresolved issues note
