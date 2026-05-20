# Repository Instructions

This repository defines a Codex subagent workflow for AI-supported QA of Word documents.

The repo is instruction-first and agent-first. Do not create deterministic Python scripts for parsing, reviewing, applying changes, auditing, or document processing unless the user explicitly changes the project direction. `document_map_parser.py` is the one exception — it is the approved DOCX extraction helper and may be extended. Do not create a Python package. Do not use `uv`.

## Hard Rules

1. Never modify the original Word document.
2. Always work on a reviewed copy.
3. Reviewer subagents must not edit files.
4. Reviewer subagents return structured JSON issues only.
5. The Document Map Runner subagent runs `document_map_parser.py` and writes extraction outputs. It does not review or edit.
6. The Document Map subagent reads the extraction outputs and produces a human summary. It does not parse DOCX or run scripts.
7. The Issue Log Consolidator subagent deduplicates and prioritises findings but does not edit.
8. The Document Application subagent is the only subagent allowed to apply approved changes to the reviewed copy.
9. The Audit subagent must run after any document modification.
10. No silent text changes are allowed.
11. If tracked changes are requested, every textual change must be visible as a tracked change.
12. If robust tracked changes cannot be produced, stop and report the limitation rather than faking it.
13. The audit must check original preservation, tracked-change integrity, no silent XML changes, reject-all simulation where feasible, and issue-log reconciliation.
14. Use resolved paths. Never write outside the repo or approved workspace.
15. Do not invent project facts. Use only the document and supplied context files.
16. Distinguish `safe_edit`, `comment_only`, and `human_decision_required` issues.

## Fixed Workflow

1. User provides a Word document.
2. Orchestrator scopes QA using the minimum required questions. It explains which hats are chapter-level vs full-document.
3. Orchestrator creates a QA Plan including chapter count and estimated subagent count.
4. User approves or edits the QA Plan before any mapping or reviewer work begins.
5. Document extraction runs in two steps:
   - Document Map Runner runs `document_map_parser.py --output --by-chapter --term-index` and writes: `qa_run/working/document-map.json`, `qa_run/working/chapters/<chapter>.json` (one per section), `qa_run/working/term-index.json`. Validates `document-map.json` against `schemas/document-map.schema.json` using jsonschema. Fails loudly on any error; workflow stops until resolved.
   - Document Map reads `document-map.json` and writes `qa_run/working/document-map-summary.md`.
6. Selected reviewer subagents run according to their scope:
   - Chapter-level hats (proofreading, house style, references/sources): one subagent per chapter, run in parallel. Each receives only its chapter's data slice.
   - Full-document hats (terminology, numbers/tables/claims): one subagent for the whole document. Terminology receives the term-index only; numbers receives `numeric_claims` and `tables` only.
7. Chapter-level outputs are merged per hat into `qa_run/working/reviewer-outputs/<hat>-issues.json`. Full-document hat outputs write there directly.
8. Issue Log Consolidator reads from `qa_run/working/reviewer-outputs/` and creates a consolidated issue log.
9. User chooses application mode: issue-log-only, comments-only, tracked changes for safe edits and comments for everything else, rerun selected hat, or stop without applying changes.
10. Document Application subagent applies only user-approved changes to the reviewed copy.
11. Audit subagent runs after any document application.
12. Outputs: reviewed `.docx` where applicable, issue log, application log where applicable, audit report, optional unresolved issues note.

## Subagent Roles

### Orchestrator

The Orchestrator owns scoping, sequencing, user approval checkpoints, and final delivery. It must create a QA Plan before reviewer work begins and must wait for user approval before proceeding beyond the plan.

When presenting hats to the user, the Orchestrator distinguishes chapter-level hats (proofreading, house style, references/sources) from full-document hats (terminology, numbers/tables/claims) and states the estimated subagent count.

The Orchestrator must not apply document changes directly. It may create copies, route tasks, collect outputs, and prepare summaries.

### Document Map Runner Subagent

The Document Map Runner executes `document_map_parser.py` as a deterministic shell command. It writes three outputs: the full `document-map.json`, per-section `chapters/` files (each including a `footnote_map` for inline footnote resolution), and `term-index.json` (stopword-filtered term occurrence index). It then validates `document-map.json` against `schemas/document-map.schema.json`. It reports SUCCESS or FAILURE with exact error output. It does not parse DOCX XML itself and does not fall back to ad-hoc extraction on failure.

### Document Map Subagent

The Document Map subagent reads the pre-built `document-map.json` and produces a human-readable `document-map-summary.md`. It is read-only. It does not run scripts, open the DOCX file, or modify `document-map.json`.

### Reviewer Subagents

Reviewer subagents perform focused QA review. They must be read-only and must return structured JSON issues only.

**Chapter-level hats** receive a single chapter pack containing only that chapter's data slice (paragraphs for proofreading and house style; references and footnotes for references/sources). They do not receive the full document map.

**Full-document hats** receive a single pack. The terminology hat receives the term-index (term occurrences and locations) — not raw paragraphs. The numbers hat receives only `numeric_claims` and `tables`.

Each issue must distinguish whether it is:
- `safe_edit`
- `comment_only`
- `human_decision_required`

Reviewer subagents must not edit files, create reviewed copies, apply changes, or silently alter any content.

### Issue Log Consolidator Subagent

The Issue Log Consolidator merges chapter-level outputs per hat first, then deduplicates, prioritises, and normalises all reviewer findings into a single issue log. It must not edit the Word document.

It preserves traceability from consolidated findings back to source reviewer issue IDs where possible.

### Document Application Subagent

The Document Application subagent is the only subagent allowed to apply user-approved changes, and only to the reviewed copy.

It applies only changes explicitly approved by the user. It preserves unresolved, ambiguous, or human-decision issues for the unresolved issues note rather than guessing.

If tracked changes are requested and robust tracked changes cannot be produced, it stops and reports the limitation.

The default modification mode is tracked changes for `safe_edit` issues and comments for everything else.

### Audit Subagent

The Audit subagent runs after any document modification. It checks:

- the original document was preserved
- tracked-change integrity
- no silent XML changes
- reject-all simulation where feasible
- reconciliation between the issue log, approved changes, applied changes, and unresolved issues

The Audit subagent reports failures plainly and does not apply fixes itself.

## Path And File Safety

Use resolved paths for all file operations. Never write outside the repo or an explicitly approved workspace path.

Original Word documents are source artifacts. Treat them as immutable. Create reviewed copies before any application step.

Do not invent project facts. Use only the Word document and supplied context files.

## Expected Outputs

The workflow produces:

- reviewed `.docx`
- issue log (`.md` and/or `.csv`)
- audit report
- optional unresolved issues note
