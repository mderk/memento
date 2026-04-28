---
id: 03-p1-wrapper-expansion-and-release-hardening-03-finalize-rollout-docs-and-acceptance-coverage
status: pending
estimate: 2h
---
# Finalize rollout docs and acceptance coverage

## Objective

<!-- objective -->
Close the rollout with clear user-facing documentation and explicit acceptance coverage for the released command surface. This makes the new pi path understandable and supportable beyond the original implementation session.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Document the final install and usage story

Users should be able to install and use `memento-pi` without reconstructing design intent from source or session notes.

- [ ] Update README and memory notes for the final command surface
  Describe release-mode bootstrap, development fallback, `.pi/settings.json` shape, `/wf` vs `/mw` namespaces, and the expected workflow entrypoints.

- [ ] Sync the rollout checklist with implemented reality
  Mark completed items and capture any deliberate follow-up items separately instead of leaving stale checklist entries.

<!-- accept -->
- Documentation explains how to install `memento-pi`, how backend startup works, and which commands to use for generic versus project-specific workflows.
- The rollout checklist reflects the actual implementation state rather than the original aspirational backlog.
- A new contributor can discover the supported command paths and config keys without reading source code.
<!-- /accept -->
<!-- /task -->

<!-- task -->
### Verify rollout-level acceptance end to end

Run the full checks that prove the rollout goals, not just isolated unit changes.

- [ ] Run backend and extension regression suites
  Use the existing Python and TypeScript verification commands as the release gate for the integrated path.

- [ ] Spot-check the key acceptance flows from the rollout plan
  Confirm `/wf list`, `/wf resume`, `/mw create-protocol`, `/mw process-protocol`, and `/mw develop` all work through the intended backend path.

<!-- accept -->
- The documented rollout acceptance flows are all verifiable through the real path: command -> extension -> backend workflow.
- Backend and extension regression suites pass together after the final docs and wrapper changes.
- Any remaining out-of-scope items are explicitly deferred instead of left as silent gaps.
<!-- /accept -->
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Do not introduce new workflow behavior in the finalization step; focus on documentation, validation, and explicit follow-ups.
- Use the real integrated path for acceptance checks rather than mocked shortcuts.
- Capture any remaining non-goals or follow-up work separately from the rollout completion criteria.
<!-- /constraints -->

## Implementation Notes

This step is the release-quality pass for the whole protocol. It should leave the docs, checklists, and tests aligned so future sessions do not need to reverse-engineer what 'done' means for the pi rollout.

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
The rollout plan defines acceptance separately for P0a, P0, and P1. This final step consolidates those checks into a documented release-ready validation pass.
<!-- /context:inline -->

<!-- context:files -->
- memento-pi/memory/pi-rollout-plan.md
- memento-pi/memory/pi-rollout-checklist.md
- memento-pi/README.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-pi/README.md
- memento-pi/memory/pi-rollout-checklist.md
- memento-pi/tests/
- memento-workflow/tests/
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] memento-pi/memory/pi-rollout-checklist.md
- [ ] memento-pi/memory/README.md
- [ ] .memory_bank/tech_stack.md
