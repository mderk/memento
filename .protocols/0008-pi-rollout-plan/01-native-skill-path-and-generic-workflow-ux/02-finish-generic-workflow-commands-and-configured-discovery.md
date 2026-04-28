---
id: 01-native-skill-path-and-generic-workflow-ux-02-finish-generic-workflow-commands-and-configured-discovery
status: pending
estimate: 2h
---
# Finish generic workflow commands and configured discovery

## Objective

<!-- objective -->
Complete the generic `/wf` command surface so pi can manage workflow runs cleanly outside of wrapper commands. This closes the remaining gap between the backend resume/config work already landed and the user-facing command UX that still needs to consume it.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Expose backend resume cleanly in `/wf`

The backend `resume(run_id, cwd, workflow_dirs)` method already exists; the extension command surface should use it directly.

- [ ] Add `/wf resume <run_id>`
  Call the backend `resume(...)` method with the current working directory and configured workflow directories, then hand the returned action stream to the same runtime loop used by fresh starts.

- [ ] Improve `/wf reload` and run recovery messaging
  When reload drops active runtime state, give the user a clear path to resume using the run id. Ensure the wording matches the actual command surface.

- [ ] Add integration coverage for resume flows
  Exercise create/reload/resume behavior so the runtime command path proves that the extension does not need to parse checkpoint internals itself.

<!-- accept -->
- `/wf resume <run_id>` resumes a run through the backend without requiring the extension to infer the workflow name from checkpoint files.
- Reload/recovery messaging points users to the actual resume path the extension supports.
- Resume behavior is covered by automated integration tests.
<!-- /accept -->
<!-- /task -->

<!-- task -->
### Wire configured `workflowDirs` into generic workflow operations

The config surface now supports extra workflow directories; the command layer should actually pass them through everywhere it matters.

- [ ] Pass `workflowDirs` to `list_workflows`, `start`, and `resume`
  Keep project `.workflows/` auto-discovery intact while allowing external workflow packs from config to participate in generic workflow UX.

- [ ] Add config-level regression coverage for discovery behavior
  Ensure configured workflow directories continue to affect generic workflow commands after future refactors.

<!-- accept -->
- Configured `workflowDirs` affect `/wf list`, `/wf start`, and `/wf resume` consistently.
- Project-local `.workflows/` discovery still works alongside configured extra workflow directories.
- The extension command layer does not silently ignore configured workflow directories.
<!-- /accept -->
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Keep the generic `/wf` namespace focused on workflow control rather than project-specific convenience logic.
- Do not reintroduce pi-side checkpoint parsing or workflow-name inference.
- Preserve existing successful wrapper behavior while finishing the generic command surface.
<!-- /constraints -->

## Implementation Notes

This is now a narrower step than the original P0 plan because the backend resume API already exists. The work left is mostly command wiring, test coverage, and user-facing polish.

## Verification

<!-- verification -->
```bash
cd memento-pi && npm run typecheck
cd memento-pi && npm run test:integration
cd memento-workflow && uv run pytest
```
<!-- /verification -->

## Context

<!-- context:inline -->
The current code already exposes compat `resume` tools, but the `/wf` command implementation still needs to catch up to the backend/runtime capabilities that now exist.
<!-- /context:inline -->

<!-- context:files -->
- memento-pi/memory/pi-rollout-plan.md
- memento-pi/memory/pi-rollout-checklist.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-pi/src/index.ts
- memento-pi/src/config.ts
- memento-workflow/scripts/runner.py
- memento-workflow/scripts/server.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] memento-pi/memory/pi-rollout-checklist.md
- [ ] memento-pi/memory/decisions.md
