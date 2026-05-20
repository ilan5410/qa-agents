# Scoping Questions

The Orchestrator should ask only the minimum questions needed to create a QA Plan.

If the user has already provided an answer, do not ask again. Use defaults where allowed.

## Default Questions

1. What Word document should I review?

2. What type of output is this?
   - expert report
   - client report
   - regulatory submission
   - proposal
   - internal note
   - other

3. What stage is it at?
   - outline
   - early draft
   - detailed draft
   - near-final
   - final QA

4. What review mode do you want?
   - quick clean-up
   - full technical QA
   - numbers and consistency only
   - style and proofreading only
   - references and sources only
   - custom

5. How should changes be handled?
   - issue log only
   - comments only
   - tracked changes for safe edits and comments for everything else
   - ask me before any document changes

6. Do you have optional context files?
   - project context note
   - style guide
   - terminology list
   - proposal / scope document
   - previous version
   - model output summary

## Defaults

- Output type: ask if missing.
- Stage: ask if missing.
- Review mode: full technical QA.
- Change handling: tracked changes for safe edits and comments for everything else.
- Optional context: none unless supplied.
- Full technical QA uses the stronger canonical reviewers by default: `footnote_proofreader_update`, `style_proofreader`, `technical_proofreader`, `terminology_reviewer`, and `numbers_tables_claims_reviewer`. Legacy fallback reviewers are excluded unless the user explicitly asks for them.

## Minimum-Question Rule

Ask only for information that is missing and needed for the next step.

Examples:

- If the user provides a Word document but no output type or stage, ask only for output type and stage.
- If the user asks for numbers-only review, use review mode `numbers and consistency only` and do not ask about reviewer hats.
- If the user asks for issue-log-only output, do not ask tracked-change questions unless they later choose application.
- If optional context files are not mentioned, proceed without them and note that the review is less calibrated for style, terminology, source, or scope-specific checks.

## QA Plan Handoff

After scoping, create a QA Plan and ask the user to approve or edit it before invoking the Document Map subagent or any reviewer subagent.
