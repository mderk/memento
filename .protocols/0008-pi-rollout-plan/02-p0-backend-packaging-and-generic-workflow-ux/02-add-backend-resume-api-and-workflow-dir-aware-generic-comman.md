---
id: 02-p0-backend-packaging-and-generic-workflow-ux-02-add-backend-resume-api-and-workflow-dir-aware-generic-comman
status: pending
estimate: 2h
---
# Add backend resume API and workflow-dir aware generic commands

## Objective

<!-- objective -->
Move resume semantics fully into `memento-workflow`, then expose them through the generic pi workflow controls. This removes pi-side guesswork about workflow names and checkpoint metadata.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Implement backend-owned resume semantics

The extension should provide a run id and working directory; the backend should do the rest.

- [ ] Add `resume(run_id, cwd, workflow_dirs=[])` to the runner/server surface
  Load checkpoint metadata server-side, resolve the workflow name internally, and return the next action envelope in the same shape as other methods.

- [ ] Register and test the new backend method
  Update dispatch tables and integration coverage so resume is available everywhere the server exposes JSONL methods.

<!-- accept -->
- Calling `resume(run_id, cwd, workflow_dirs)` works without the caller supplying the workflow name.
- The returned action envelope matches the shape used by `start` and `submit` so the relay path does not need special handling.
- Unknown or invalid run ids fail with clear backend errors instead of undefined behavior in pi.
<!-- /accept -->
<!-- /task -->

<!-- task -->
### Wire workflow dirs and resume into `/wf` commands

Generic workflow commands should discover external workflow packs and expose resume consistently.

- [ ] Pass configured `workflowDirs` to `list`, `start`, and `resume`
  Keep project `.workflows/` auto-discovery intact while allowing extra workflow directories from config.

- [ ] Add `/wf resume <run_id>`
  Call the backend `resume(...)` API directly and let the standard relay handle the returned action sequence.

- [ ] Add integration coverage for generic resume flows
  Exercise the command surface end to end so the extension does not need to inspect checkpoints itself.

<!-- accept -->
- `/wf resume <run_id>` resumes a prior run using only the run id, current cwd, and configured workflow dirs.
- Configured `workflowDirs` affect `/wf list`, `/wf start`, and `/wf resume` consistently.
- The extension does not read checkpoint files directly to determine workflow identity.
<!-- /accept -->
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Backend owns checkpoint lookup and workflow-name resolution.
- Do not add pi-side parsing of checkpoint internals.
- Keep the generic `/wf` surface stable while adding resume support.
<!-- /constraints -->

## Implementation Notes

This is the architectural boundary the rollout plan emphasizes most strongly. If a shortcut requires `memento-pi` to infer workflow names from checkpoint files, reject it and fix the backend contract instead.

## Verification

<!-- verification -->
```bash
cd memento-workflow && uv run pytest
cd memento-workflow && uv run pyright
cd memento-pi && npm run typecheck
cd memento-pi && npm run test:integration
```
<!-- /verification -->

## Context

<!-- context:inline -->
Backlog items A and C are coupled here: once backend resume exists, pi can expose `/wf resume` and pass configured workflow dirs to all generic workflow calls.
<!-- /context:inline -->

<!-- context:files -->
- memento-pi/memory/pi-rollout-plan.md
- memento-pi/memory/pi-rollout-checklist.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-workflow/scripts/runner.py
- memento-workflow/scripts/server.py
- memento-pi/src/index.ts
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] memento-pi/memory/pi-rollout-checklist.md
- [ ] memento-pi/memory/decisions.md
