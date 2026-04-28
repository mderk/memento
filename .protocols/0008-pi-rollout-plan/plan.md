---
status: Draft
---
# Protocol: memento-pi rollout

**Status**: Draft
**Created**: 2026-04-29
**PRD**: [./prd.md](./prd.md)

## Context

The original rollout plan covered a broad P0a/P0/P1 backlog. Since then, key foundations have landed: protocol wrappers for `create-protocol` and `process-protocol`, backend `resume(...)`, packaged server entrypoint, `.pi/settings.json` `memento` config, compat workflow tools, and working model alias/thinking configuration for subagents. The protocol should now focus on the remaining gaps that block a clean claim that existing project skills and workflow entrypoints run natively in pi.

## Decision

Replace the broad initial rollout backlog with a delta plan focused on the unfinished pieces:

- **native skill path hardening**: prove that existing project skills can drive the real workflow backend through `memento-pi`, including subagent steps and live session reload behavior
- **generic workflow UX completion**: finish `/wf resume`, wire `workflowDirs`, and complete release-mode backend bootstrap defaults
- **wrapper and release completion**: add the remaining high-value `/mw` wrappers, then refresh docs/checklists to match reality

This keeps the existing backend API and shared `.workflows/` definitions intact while narrowing implementation work to the remaining runtime, command-surface, and documentation gaps.

## Rationale

The old protocol is now partially obsolete because many of its early steps are already complete. Keeping them in the active protocol would create noise and make progress tracking misleading. A smaller delta protocol is easier to execute and better aligned with the real acceptance target: existing project skills and workflow entrypoints should work in pi without manual backend handling or ad-hoc workarounds. Alternatives such as leaving the stale protocol in place or starting a separate unrelated protocol would either hide current reality or fragment the rollout history.

## Consequences

### Positive

- The updated protocol tracks only remaining rollout work instead of mixing completed and incomplete milestones.
- Native skill execution, generic workflow UX, and wrapper completion become explicit acceptance targets rather than implicit assumptions.
- The release story can be documented against the real implemented behavior, including model alias and thinking-level configuration.

### Negative

- Historical P0a/P0/P1 framing becomes less directly visible in the active protocol; mitigate this by preserving the prior PRD and plan history in the protocol directory and memory notes.
- The remaining steps are more cross-cutting and require careful verification across live sessions, commands, and backend behavior; mitigate with focused integration coverage and explicit smoke checks.
- There is a temptation to expand scope into larger relay-runtime redesign; mitigate by treating relay simplification as a follow-up unless it is required to satisfy the stated acceptance criteria.

## Progress

### Native skill path and generic workflow UX (01-native-skill-path-and-generic-workflow-ux/)

- [ ] [Harden native existing-project skill execution](./01-native-skill-path-and-generic-workflow-ux/01-harden-native-existing-project-skill-execution.md) <!-- id:01-native-skill-path-and-generic-workflow-ux-01-harden-native-existing-project-skill-execution --> — 2h30m est

- [ ] [Finish generic workflow commands and configured discovery](./01-native-skill-path-and-generic-workflow-ux/02-finish-generic-workflow-commands-and-configured-discovery.md) <!-- id:01-native-skill-path-and-generic-workflow-ux-02-finish-generic-workflow-commands-and-configured-discovery --> — 2h est

- [ ] [Complete release-mode bootstrap and config documentation](./01-native-skill-path-and-generic-workflow-ux/03-complete-release-mode-bootstrap-and-config-documentation.md) <!-- id:01-native-skill-path-and-generic-workflow-ux-03-complete-release-mode-bootstrap-and-config-documentation --> — 2h30m est

### Wrapper surface completion and rollout closure (02-wrapper-surface-completion-and-rollout-closure/)

- [ ] [Add `/mw develop` and reusable wrapper scaffolding](./02-wrapper-surface-completion-and-rollout-closure/01-add-mw-develop-and-reusable-wrapper-scaffolding.md) <!-- id:02-wrapper-surface-completion-and-rollout-closure-01-add-mw-develop-and-reusable-wrapper-scaffolding --> — 1h30m est

- [ ] [Add the remaining high-value `/mw` wrappers](./02-wrapper-surface-completion-and-rollout-closure/02-add-the-remaining-high-value-mw-wrappers.md) <!-- id:02-wrapper-surface-completion-and-rollout-closure-02-add-the-remaining-high-value-mw-wrappers --> — 3h est

- [ ] [Run final rollout acceptance and close the protocol](./02-wrapper-surface-completion-and-rollout-closure/03-run-final-rollout-acceptance-and-close-the-protocol.md) <!-- id:02-wrapper-surface-completion-and-rollout-closure-03-run-final-rollout-acceptance-and-close-the-protocol --> — 2h est
