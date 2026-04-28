---
id: 01-p0a-dogfood-protocol-workflows-01-add-protocol-resolution-helpers-and-create-protocol-wrapper
status: pending
estimate: 2h
---
# Add protocol resolution helpers and create-protocol wrapper

## Objective

<!-- objective -->
Make pi resolve protocol inputs the same way the existing project skill does, then launch the real `create-protocol` workflow without reimplementing workflow logic. This establishes the first dogfood path for protocol generation against local project workflows.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Implement shared protocol input resolution

Support the same input shapes that the existing skill supports so wrapper commands and skills converge on one deterministic path.

- [ ] Add helpers for protocol number, protocol path, PRD file path, and free-text task description
  Return a normalized object containing at least `protocol_dir` and `prd_source`. Existing `prd.md` should produce an empty `prd_source`; free-text input should preserve the original description for workflow generation.

- [ ] Allocate the next protocol number deterministically
  Mirror the skill behavior by inspecting `.protocols/`, zero-padding the next number, and deriving a stable slug for new protocol directories.

- [ ] Fail clearly on unsupported or ambiguous inputs
  Surface actionable error messages when a protocol number does not exist, a provided path lacks `prd.md`, or multiple matches would be possible.

<!-- accept -->
- Given an existing protocol number like `8` or `008`, the helper resolves the matching `.protocols/.../prd.md` and returns that protocol directory.
- Given a free-text request, the helper creates a new numbered protocol directory plan and returns a non-empty `prd_source` without requiring a pre-existing `prd.md`.
- Invalid protocol references fail with a clear user-facing message instead of starting the workflow with bad variables.
<!-- /accept -->
<!-- /task -->

<!-- task -->
### Expose `/mw create-protocol` as a thin workflow wrapper

The wrapper should do only pre-start resolution and then hand off to the existing backend workflow and relay machinery.

- [ ] Validate wrapper input before start
  Reject empty invocations and ensure resolved variables are coherent before calling the backend.

- [ ] Start the existing `create-protocol` workflow with resolved variables
  Call `start(workflow="create-protocol", variables={ protocol_dir, prd_source, workdir })` and let the relay path handle the rest. Do not duplicate protocol rendering logic in pi.

- [ ] Add integration coverage for the wrapper path
  Exercise wrapper resolution plus the backend start contract in the existing integration harness.

<!-- accept -->
- `/mw create-protocol <description>` starts the real `create-protocol` workflow with the expected `protocol_dir`, `prd_source`, and `workdir` variables.
- `/mw create-protocol <existing protocol ref>` reuses the existing protocol directory and passes an empty `prd_source`.
- The wrapper does not generate protocol files itself; all file creation still comes from the backend workflow.
<!-- /accept -->
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Keep current dev bootstrap behavior; do not block dogfood work on release packaging.
- Do not duplicate logic from `.workflows/create-protocol` in the pi wrapper.
- Preserve existing generic `/wf` commands and current skill/workflow layouts.
<!-- /constraints -->

## Implementation Notes

Prefer a dedicated helper module (for example `src/commands/protocols.ts`) so `create-protocol`, `process-protocol`, and later wrappers share one resolution implementation. Mirror the skill contract exactly to avoid subtle differences between `/skill:create-protocol` and `/mw create-protocol`.

## Verification

<!-- verification -->
```bash
cd memento-pi && npm run typecheck
cd memento-pi && npm run test:integration
```
<!-- /verification -->

## Context

<!-- context:inline -->
This step implements the P0a backlog items for protocol helpers and `/mw create-protocol`. The rollout plan explicitly says wrapper commands should do only pre-start logic and then call the existing workflow backend.
<!-- /context:inline -->

<!-- context:files -->
- memento-pi/memory/pi-rollout-plan.md
- memento-pi/memory/pi-rollout-checklist.md
- .agents/skills/create-protocol/SKILL.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-pi/src/index.ts
- memento-pi/tests/protocol-wrappers.integration.test.ts
- .workflows/create-protocol/workflow.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] memento-pi/memory/pi-rollout-checklist.md
- [ ] memento-pi/README.md
