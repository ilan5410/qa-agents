# Codex Word QA Workflow

This repository defines an agent-first Codex workflow for AI-supported QA of Word documents.

It is not a deterministic Python document processor. The workflow is expressed through Codex subagent definitions, schemas, examples, and operating instructions. Python tooling may be added later for lightweight schema validation, but the core review and application process is intentionally orchestrated by Codex agents.

## Workflow

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

## Subagents

- `document_map` extracts headings, paragraphs, tables, footnotes, references, source notes, and numeric claims. It does not review or edit.
- `document_map_parser.py` is the package-aware helper used for the actual DOCX traversal.
- `proofreading_reviewer` identifies low-risk mechanical drafting issues such as typos, grammar, repeated words, spacing, and punctuation.
- `house_style_reviewer` checks UK English, Frontier style guide compliance where supplied, tone, preferred wording, labels, and supplied examples.
- `references_sources_reviewer` checks references, sources, footnotes, cross-references, placeholders, missing source notes, and unsupported claims.
- `terminology_reviewer` checks defined terms, acronyms, party names, market names, and terminology consistency.
- `numbers_tables_claims_reviewer` checks internal consistency of numbers, percentages, units, tables, figures, and quantified claims.
- `issue_log_consolidator` validates, deduplicates, prioritises, groups, and formats reviewer outputs.
- `document_application` applies only user-approved changes to the reviewed copy and produces an application log.
- `audit` checks original preservation, tracked-change integrity, silent XML changes, reject-all feasibility, and issue-log reconciliation.

Subagent drafts currently live in `codex/subagents/`. The official Codex project-scoped location is `.codex/agents/`; in this workspace that folder has a local write restriction, so the TOML files are staged in the repo-visible draft folder until the ACL is fixed.

## Safety Model

- The original Word document is never modified.
- All document modification happens only on a reviewed copy.
- Reviewer subagents do not edit files.
- Reviewer subagents return structured JSON issues only.
- No silent text changes are allowed.
- Tracked changes are used only if they can be produced robustly.
- If robust tracked changes cannot be guaranteed, the workflow stops or falls back to comments-only only after telling the user.
- The default modification mode is tracked changes for safe edits and comments for everything else.
- Judgement-heavy issues are not automatically rewritten.
- The Audit subagent must run after any document application step.

## How To Use In Codex

1. Start with the QA Orchestrator.
2. Provide the Word document path.
3. Answer the minimum scoping questions.
4. Review and approve or edit the QA Plan.
5. Let the Orchestrator run the Document Map and selected reviewer subagents.
6. Inspect the consolidated issue log.
7. Choose the application mode:
   - issue log only
   - comments only
   - tracked changes for safe edits and comments for everything else
   - rerun selected reviewer hat
   - stop without applying changes
8. If applying changes, approve the application choices.
9. Inspect the reviewed `.docx`, issue log, application log, unresolved issues note if created, and audit report.

## Repository Layout

- `AGENTS.md` contains the operating rules for this repository.
- `document_map_parser.py` contains the DOCX extraction helper used by the document-map workflow.
- `codex/subagents/` contains the staged Codex subagent TOML definitions.
- `codex/workflows/` contains workflow guidance for scoping and reruns.
- `schemas/` contains JSON schemas for QA plans, document maps, issues, issue logs, application plans, and audit reports.
- `examples/` contains matching example JSON files.
- `prompts/`, `docs/`, and `tests/` are reserved for future workflow material and validation fixtures.

## Known Limitations

- Tracked changes may depend on the available Codex and Word document environment capabilities.
- Reject-all simulation may not always be technically available.
- The Numbers, Tables and Quantified Claims reviewer checks internal consistency, not truth.
- The House Style reviewer is only fully calibrated when a style guide or examples are supplied.
- Source and citation review depends on the supplied document map, source list, and context files.
