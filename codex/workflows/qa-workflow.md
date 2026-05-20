# QA Workflow

This is the fixed workflow for the Codex Word QA process. README.md, AGENTS.md, and this file should describe these steps consistently.

## Fixed Workflow

1. User provides a Word document.
2. Orchestrator scopes QA using the minimum required questions.
3. Orchestrator checks for previous-run artifacts and lists the exact cleanup set before any deletion:
   - `qa_run/working/document-map.json`
   - `qa_run/working/document-map-summary.md`
   - `qa_run/working/qa-plan.json`
   - `qa_run/working/application-plan.json`
   - `qa_run/working/issue-log.md`
   - `qa_run/working/issue-log.csv`
   - `qa_run/working/application_log.json`
   - `qa_run/working/audit-report.json`
   - `qa_run/working/audit-report.md`
   - `qa_run/working/unresolved_issues.md`
   - `qa_run/working/*.reviewed.docx`
   - `qa_run/working/reviewer-packs/` (any files)
   - `qa_run/outputs/` (any files)
   - any `qa_run/working/docx_package_*` directories
4. Orchestrator creates a QA Plan.
5. User approves or edits the QA Plan before any mapping or reviewer work begins.
6. Document Map subagent extracts structure and claims without reviewing or editing.
7. Selected reviewer subagents run and return JSON issues matching `schemas/issue.schema.json`.
8. Issue Log Consolidator creates a consolidated issue log.
9. User chooses application mode: issue-log-only, comments-only, tracked changes for safe edits and comments for everything else, rerun selected hat, or stop without applying changes.
10. Document Application subagent applies only user-approved changes to the reviewed copy.
11. Audit subagent runs after any document application.
12. Outputs are reviewed `.docx` where applicable, issue log, application log where applicable, audit report where applicable, and optional unresolved issues note.

## Default Modification Mode

The default modification mode is tracked changes for safe edits and comments for everything else.

If tracked changes cannot be guaranteed, the workflow must stop and tell the user. It may fall back to comments-only only after user approval.

## Non-Application Modes

The workflow supports:

- issue-log-only output
- comments-only output
- rerunning one reviewer hat
- rerunning all hats on a selected section
- stopping without applying changes
