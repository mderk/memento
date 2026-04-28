---
id: 01-p0a-dogfood-protocol-workflows-02-add-process-protocol-wrapper-with-resume-or-fresh-ux
status: pending
estimate: 2h30m
---
# Add process-protocol wrapper with resume-or-fresh UX

## Objective

<!-- objective -->
Let pi start the existing `process-protocol` workflow against a resolved protocol directory and handle the `.last_run` resume decision through pi-native user prompts. This completes the P0a dogfood loop for real protocol execution.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Resolve protocol directories for process-protocol

Reuse the shared helpers, but tailor validation to the execution use case.

- [ ] Support number, explicit path, and description-based matching
  Description-based matching should search protocol metadata such as `plan.md` consistently with the rollout plan.

- [ ] Verify the resolved protocol is executable
  Require `plan.md` before starting `process-protocol` and report a clear error if the protocol has not been generated yet.

<!-- accept -->
- `/mw process-protocol <number>` resolves the matching protocol directory and refuses to start if `plan.md` is missing.
- Description-based resolution selects the intended protocol deterministically or reports that the match is ambiguous.
- The wrapper passes the resolved `protocol_dir` to the backend without mutating protocol files locally.
<!-- /accept -->
<!-- /task -->

<!-- task -->
### Implement `.last_run` resume handling

Resume semantics should stay backend-owned, but the pi wrapper needs to ask the user which path to take when previous run state exists.

- [ ] Inspect `.last_run` in the protocol directory
  Read the run id pointer if it exists and treat it as a hint, not as checkpoint data to parse in the extension.

- [ ] Prompt the user to resume or start fresh
  Use pi UI selection/confirmation primitives to present a clear choice and then pass either `resume=<run_id>` or a fresh start request.

- [ ] Cover the resume/fresh flow with integration tests
  Include both branches so `.last_run` handling is stable before broader rollout work continues.

<!-- accept -->
- When `.last_run` is present, the wrapper asks whether to resume or start fresh before calling the backend.
- Choosing resume starts the real `process-protocol` workflow with the prior run id instead of trying to reconstruct state in pi.
- Choosing fresh ignores `.last_run` and starts a new backend run for the same protocol directory.
<!-- /accept -->
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Do not parse checkpoint files in `memento-pi`; only inspect the `.last_run` pointer.
- Keep the existing local backend fallback for dogfood mode.
- Use real user prompts rather than hidden defaults for resume-vs-fresh decisions.
<!-- /constraints -->

## Implementation Notes

This step should finish the P0a acceptance path described in the rollout plan. If wrapper code starts to grow, move protocol-specific logic out of `src/index.ts` into dedicated command modules before adding more wrappers.

## Verification

<!-- verification -->
```bash
cd memento-pi && npm run typecheck
cd memento-pi && npm run test:integration
```
<!-- /verification -->

## Context

<!-- context:inline -->
The rollout plan calls out `.last_run` as the key UX requirement for `process-protocol`. Backend state ownership still belongs to `memento-workflow`; pi only decides which start path to invoke.
<!-- /context:inline -->

<!-- context:files -->
- memento-pi/memory/pi-rollout-plan.md
- memento-pi/memory/pi-rollout-checklist.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-pi/src/index.ts
- memento-pi/tests/protocol-wrappers.integration.test.ts
- memento-pi/tests/helpers/harness.ts
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] memento-pi/memory/pi-rollout-checklist.md
- [ ] memento-pi/memory/runtime-notes.md
