---
id: 01-native-skill-path-and-generic-workflow-ux-01-harden-native-existing-project-skill-execution
status: pending
estimate: 2h30m
---
# Harden native existing-project skill execution

## Objective

<!-- objective -->
Make the direct skill path the primary accepted route for existing project workflows in pi. This step should prove that a user can invoke an existing project skill such as `/skill:create-protocol`, have it reach the real `memento-workflow` backend through `memento-pi` tools, and survive subagent/reload edge cases without falling back to manual simulation.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Codify native skill acceptance for real workflows

The project goal is now broader than wrapper commands: existing discovered skills must also work natively through the extension tool surface.

- [ ] Define the expected skill-to-backend path explicitly
  Document and enforce the intended chain: discovered project skill -> registered compat tools (`start`, `submit`, `next`, `AskUserQuestion`, `Agent`) -> real backend workflow. Clarify that creating protocol files by hand or manually simulating workflow state is not an acceptable fallback for rollout acceptance.

- [ ] Add smoke coverage or scripted validation for direct skill invocation
  Exercise a real existing skill path such as `create-protocol` against project workflows and verify that the backend produces the expected action sequence. If fully automated skill invocation is awkward in the current harness, add the thinnest reliable regression mechanism possible and document any remaining manual acceptance step explicitly.

- [ ] Capture the live-session expectations around reload and tool visibility
  Record how extension reload/new-session behavior affects tool availability so future debugging does not repeat the same discovery work. Focus on the real operator workflow: reload, confirm tools are present, then run the skill.

<!-- accept -->
- A real existing project skill can start the intended backend workflow through `memento-pi` without manual workflow simulation.
- The accepted path is documented as skill -> extension tools -> backend workflow, and hand-created protocol output is explicitly excluded from acceptance.
- Reload/new-session expectations for extension tool visibility are documented or covered well enough to reproduce the path reliably.
<!-- /accept -->
<!-- /task -->

<!-- task -->
### Stabilize subagent startup on the native path

Native skill execution is only convincing if subagent steps use configured models successfully instead of failing on stale defaults.

- [ ] Verify alias and thinking-level resolution on real subagent steps
  Use the new `memento` config shape to prove that `sonnet`, `haiku`, and `opus` aliases resolve to the configured model specs and thinking levels when a workflow launches `Agent` or relay sub-sessions.

- [ ] Add regression coverage for config-driven subagent model selection
  Keep the current object-form alias and `defaultThinkingLevel` behavior tested so future config changes cannot silently restore stale provider defaults.

- [ ] Document the expected fallback behavior
  Clarify when inline fallback is acceptable (for resilience) versus when a subagent startup failure should be considered a rollout blocker.

<!-- accept -->
- A workflow subagent step can start successfully using model aliases resolved from `.pi/settings.json` `memento` config.
- Per-alias `thinkingLevel` settings are exercised by tests or equivalent regression coverage.
- Fallback behavior is documented as resilience, not as the primary success path for native skill execution.
<!-- /accept -->
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Do not replace the existing backend workflow engine or manually emulate workflow state transitions in the extension.
- Keep existing project skills and shared `.workflows/` definitions unchanged unless a real incompatibility requires a targeted fix.
- Treat relay-runtime redesign as out of scope unless it is necessary to satisfy native skill acceptance.
<!-- /constraints -->

## Implementation Notes

This step is the rollout pivot from wrapper-only validation to direct existing-skill validation. The most important thing is to make the accepted path explicit and reproducible, not to build a perfect new abstraction layer.

## Verification

<!-- verification -->
```bash
cd memento-pi && npm run typecheck
cd memento-pi && npm run test:integration
```
<!-- /verification -->

## Context

<!-- context:inline -->
The original blocker was that the extension loaded but live session tool surfaces did not clearly expose the compat tools. Since that has been resolved in practice, the remaining work is to encode that success path as a real acceptance target and regression surface.
<!-- /context:inline -->

<!-- context:files -->
- memento-pi/memory/pi-rollout-plan.md
- memento-pi/memory/pi-rollout-checklist.md
- .agents/skills/create-protocol/SKILL.md
- .agents/skills/workflow-engine/SKILL.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-pi/src/index.ts
- memento-pi/src/llm-step.ts
- memento-pi/src/relay-session.ts
- memento-pi/tests/
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] memento-pi/memory/pi-rollout-checklist.md
- [ ] memento-pi/memory/runtime-notes.md
- [ ] memento-pi/memory/decisions.md
