# Rerun Loop Workflow

After the first issue log is produced, the user may choose a rerun or stop path before any application step.

## User Choices

The orchestrator should ask the user to choose one or more of:

1. Rerun one reviewer hat.
2. Rerun all hats on a selected section.
3. Rerun only unresolved high-severity issues.
4. Switch from tracked changes to comments-only.
5. Export issue log only.
6. Stop without applying changes.

## Rerun Rules

- Reruns must preserve the original issue log.
- New issues must receive new IDs.
- Superseded issues must be marked as `resolved` or `replaced`, not deleted.
- The Issue Log Consolidator must produce a new issue log version after each rerun.
- The Document Application subagent must only use the latest user-approved issue log.
- Reviewer subagents remain read-only during reruns.
- Reruns must not modify the original document or the reviewed copy.

## Recommended Flow

1. Preserve the current issue log as the prior version.
2. Record the user-selected rerun scope:
   - reviewer hat
   - section
   - unresolved high-severity issue IDs
   - output mode change
3. Run only the required Document Map or reviewer subagents for the selected scope.
4. Send the prior issue log, rerun outputs, QA Plan, and document map to the Issue Log Consolidator.
5. The Consolidator creates a new issue log version that:
   - preserves prior issue IDs
   - assigns new IDs to new issues
   - marks superseded issues as `resolved` or `replaced`
   - keeps rejected issues visible unless the user asks to hide them from the working view
   - clearly identifies unresolved high-priority issues
6. Ask the user to approve the new issue log version before any application step.
7. If the user chooses application, pass only the latest approved issue log to the Document Application subagent.

## Switching To Comments-Only

If the user switches from tracked changes to comments-only:

- Do not apply tracked changes.
- Preserve the issue log history.
- Mark the application mode change in the QA Plan or application plan.
- Ask the user to approve the comments-only application plan.
- The Audit subagent must still run after any comments are added to the reviewed copy.

## Export Or Stop Paths

If the user chooses `export issue log only`, produce the latest issue log and do not invoke the Document Application subagent.

If the user chooses `stop without applying changes`, preserve the latest issue log and any audit-free workflow notes, then stop. No document modification should occur.

