# Tracked Changes Safeguards

This workflow treats tracked changes as a safety feature, not a formatting preference.

## Policy

- Safe mechanical edits may be applied as tracked changes.
- Comments are used for uncertain or judgement-heavy issues.
- Numbers are never automatically corrected.
- Economic or substantive changes are never automatically rewritten.
- If tracked changes cannot be guaranteed, the workflow must not silently edit the document.
- The Document Application subagent must produce an application log.
- The Audit subagent must run after any document modification.

## Safe Mechanical Edits

Safe mechanical edits are narrow, local, and meaning-preserving. Examples may include obvious typos, repeated words, punctuation spacing, or clear capitalisation consistency.

Even safe mechanical edits require user approval before application.

## Comments Instead Of Edits

Comments should be used for:

- uncertain issues
- judgement-heavy issues
- source-dependent issues
- terminology decisions
- tone or phrasing suggestions
- human-decision issues
- numeric inconsistencies or manual verification items

Comments must include the relevant issue ID.

## Numbers And Substantive Meaning

Numbers are never automatically corrected. This includes:

- numbers
- percentages
- percentage points
- currencies
- units
- dates
- signs
- denominators
- table values
- quantified claims

Economic, legal, analytical, or substantive changes are never automatically rewritten. If a change could affect meaning, it must be handled as a comment or human-decision issue unless the user provides exact approved wording.

## No Silent Editing

If tracked changes are requested but cannot be produced robustly, the workflow must stop and explain the limitation.

The workflow may fall back to comments-only only after the user explicitly approves that fallback.

Direct text replacement without tracked-change visibility is not allowed.

## Reject-All Safety Gate

After document application, the reviewed copy must be checked by simulating reject-all tracked changes and comparing the resulting visible text to the original document.

If any visible text difference remains after reject-all, the workflow must treat it as an untracked/silent edit:

- record the failed reject-all simulation in `application_log.json`
- set `silent_text_changes_detected` to true
- return a non-zero application status for deterministic application runs
- require audit to return `FAIL`

Comments and tracked-change markup may change the package, but they must not change the reject-all visible text baseline.

## Application Log

The Document Application subagent must produce an application log that records:

- original document path
- reviewed copy path
- output document path
- application mode
- applied issue IDs
- comment-only issue IDs
- skipped issue IDs
- unresolved issue IDs
- rejected issue IDs
- whether tracked changes were requested
- whether tracked changes were produced
- fallback decisions
- reject-all simulation result
- whether silent text changes were detected
- warnings
- failures

## Audit Requirements

The Audit subagent must check:

1. Original unchanged.
2. All textual changes tracked.
3. No silent XML changes.
4. Reject-all simulation where feasible.
5. Issue-log reconciliation.

## Failure And Warning Rules

The audit must return `FAIL` if:

- the original was modified
- untracked textual changes are detected
- rejected issues were applied
- tracked changes were requested but tracked-change integrity failed
- applied changes or comments cannot be mapped to approved issue IDs

The audit must return `WARN` if:

- reject-all simulation is unavailable
- comments-only fallback was used after user approval
- some non-critical checks could not be completed, but no silent changes were detected

If the audit fails, the workflow should recommend reverting to the original and reapplying through a safer mode.
