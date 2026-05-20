# Manual And Agentic Protocol Tests

This repo does not use deterministic Python tests for document parsing or reviewing.

Instead, it defines manual and agentic protocol tests for the Codex Word QA workflow. These tests check that the orchestrator and subagents follow the required process, preserve safety boundaries, and produce valid structured outputs.

## 1. Scoping Test

Scenario:

- User provides a Word document.
- Orchestrator asks only the required missing scoping questions.
- QA Plan is produced.
- User approves the QA Plan.

Pass criteria:

- The Orchestrator asks for missing required information only.
- The QA Plan includes document path, working copy path, output type, stage, review mode, modification mode, selected subagents, safeguards, and approval checkpoints.
- The Orchestrator does not invoke Document Map or reviewer subagents before QA Plan approval.
- The original document is not modified.

Fail criteria:

- The Orchestrator skips QA Plan approval.
- The Orchestrator asks unnecessary questions already answered by the user.
- Any document modification occurs during scoping.

## 2. Document Map Test

Scenario:

- Document contains headings, tables, footnotes, and numbers.
- Document Map subagent returns valid document-map JSON.

Pass criteria:

- Output matches `schemas/document-map.schema.json`.
- Headings and heading hierarchy are captured where available.
- Paragraphs have stable IDs such as `p_0001`.
- Tables have stable IDs such as `t_0001`.
- Footnotes and references are captured where available.
- Numeric claims preserve enough surrounding text for downstream review.
- Extraction limitations are stated clearly.
- The subagent does not review, correct, or edit the document.

Fail criteria:

- Output is not valid JSON.
- Required schema fields are missing.
- The subagent proposes edits or judgements.
- The document is modified.

## 2a. Parser Smoke Test

Scenario:

- Run `python3 document_map_parser.py qa_run/input/research_proposal_ilan_pargamin.docx --document-id doc_001 --output qa_run/working/document-map.json`.

Pass criteria:

- The command exits successfully.
- The generated JSON validates against `schemas/document-map.schema.json`.
- The output contains headings, paragraphs, footnotes, references, and numeric claims.
- No repository-tracked source file is overwritten.

## 3. Reviewer Output Test

Scenario:

- Each reviewer receives a document map and relevant optional context.
- Each reviewer returns valid issue JSON.
- No reviewer edits the document.

Pass criteria:

- Each issue matches `schemas/issue.schema.json`.
- Each reviewer uses the correct `reviewer_hat`.
- Issues include severity, confidence, location, rationale, recommended action, edit safety, status, source, and metadata.
- Reviewer outputs are JSON-only.
- Reviewer subagents do not edit files.

Fail criteria:

- A reviewer edits or creates a Word document.
- A reviewer returns unstructured prose instead of JSON issues.
- A reviewer marks judgement-heavy or numeric issues as automatic safe edits.
- Required issue fields are missing.

## 4. Consolidation Test

Scenario:

- Reviewer outputs contain duplicate or overlapping issues.
- Issue Log Consolidator merges and prioritises the outputs.
- Safe edits, comments, and human-decision issues are separated.

Pass criteria:

- Duplicate issues are merged without losing reviewer provenance.
- New or missing IDs are normalised consistently.
- High-severity issues are not suppressed unless clearly duplicated.
- Conflicts between reviewer outputs are identified.
- Safe edits, comment-only issues, and human-decision issues are clearly separated.
- Consolidated output matches `schemas/issue-log.schema.json`.
- Markdown issue log includes a CSV-compatible table.

Fail criteria:

- Distinct issues are incorrectly deleted.
- High-severity issues disappear without clear duplication.
- Reviewer rationales or recommended actions are lost.
- Comment-only or human-decision issues are converted into safe edits without justification.

## 5. Application Safety Test

Scenario:

- User approves a subset of issues for application.
- Document Application subagent applies only approved issues.
- Original remains unchanged.
- Comments and changes include issue IDs.

Pass criteria:

- The original Word document is unchanged.
- All changes are made only to the reviewed copy.
- Rejected and unapproved issues are not applied.
- Every comment or tracked change includes the relevant issue ID where technically possible.
- Numeric issues are not automatically corrected.
- `application_log.json` records applied, skipped, rejected, unresolved, and comment-only issue IDs.
- `unresolved_issues.md` is produced where relevant.

Fail criteria:

- The original document is modified.
- Unapproved or rejected issues are applied.
- Comments or changes lack issue IDs.
- Text is silently replaced.
- Numbers are corrected without explicit approved wording.

## 6. Audit Test

Scenario:

- Audit subagent receives original document, reviewed document, issue log, application log, QA Plan, and user choices.
- Audit checks for silent changes, rejected issues, and reject-all feasibility.

Pass criteria:

- Audit returns JSON matching `schemas/audit-report.schema.json`.
- Audit detects silent changes and returns `FAIL`.
- Audit detects a rejected issue applied and returns `FAIL`.
- Audit warns if reject-all simulation is unavailable.
- Audit confirms original preservation where evidence is available.
- Audit reports limitations clearly.

Fail criteria:

- Audit modifies documents.
- Audit hides unavailable checks.
- Audit returns `PASS` despite silent edits, rejected issue application, or tracked-change failure.
- Audit does not recommend reverting to original and reapplying safely after failure.

## 7. Rerun Test

Scenario:

- User chooses to rerun one reviewer hat.
- Previous issue log is preserved.
- Consolidator generates a new versioned issue log.

Pass criteria:

- Original issue log is preserved.
- Rerun scope is recorded.
- New issues receive new IDs.
- Superseded issues are marked as resolved or replaced, not deleted.
- New consolidated issue log version is produced.
- Document Application subagent uses only the latest user-approved issue log.
- No document modification occurs during rerun unless a later application step is separately approved.

Fail criteria:

- Old issue log is overwritten.
- Superseded issues are deleted.
- New issues reuse conflicting IDs.
- Application uses an unapproved or outdated issue log.
- The reviewed copy is modified during rerun without approval.
