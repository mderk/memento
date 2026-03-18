---
status: In Progress
---
# Protocol: Cleanup Shipped Content

**Status**: Draft
**Created**: 2026-03-18
**PRD**: [./prd.md](./prd.md)

## Context

The prompts and static files shipped by memento to target projects have accumulated redundancy (~40% overlap between core docs), over-investment in agent documentation (agents barely used), a generated file that should be static, and commands that should be skills. This protocol cleans up all four issues.

## Decision

Address all four issues in sequence, ordered by dependency:

1. First deduplicate prompts (foundational content, everything else references these)
2. Then clean up agents (removes files, simplifies docs)
3. Then convert testing review to static (removes a prompt, adds static files)
4. Then migrate commands to skills (structural change to manifest)
5. Finally update all indexes, README prompt, manifest, and hashes

Each step is independently verifiable. Steps within a group can be done in parallel where noted.

## Rationale

- **Sequential by dependency**: prompt deduplication must happen first because other docs reference product_brief/tech_stack/architecture
- **Agent cleanup before command migration**: both modify manifest.yaml, doing agents first is simpler (removals before additions)
- **Testing review before commands**: smaller change, reduces generated content first

Alternative considered: doing everything in one big step. Rejected — too many files changing at once, harder to verify and review.

## Consequences

### Positive

- ~40% less redundancy in core documentation
- Simpler agent story (skills instead of agent files)
- Fewer generated files (testing review competency, code-review-guidelines, ai-agent-handbook, 3 testing guides — all removed)
- Skills are self-contained (workflow co-located with SKILL.md)
- `.memory_bank/workflows/` eliminated entirely — Memory Bank is purely documentation
- Review competencies co-located with code-review workflow
- Competency injection via ShellStep — zero Read tool calls per review
- Coverage step in develop workflow catches untested code
- README ~30 lines instead of ~144 — less context window waste on `/prime`

### Negative

- Prompt changes require regeneration to verify (mitigated by testing on sample project post-protocol)
- Develop workflow changes (coverage step, test rules, explore hints) need testing across task types
- Moving workflows into skills changes the file layout users may have learned (mitigated by the layout being internal to `.claude/skills/`)

## Progress

### Deduplicate Core Docs (01-deduplicate/)

- [x] [Deduplicate prompts](./01-deduplicate/01-prompts.md) <!-- id:01-deduplicate-01-prompts --> — 2h est

### Agent Cleanup (02-agents/)

- [ ] [Remove agent-orchestration and convert agents to skills](./02-agents/01-cleanup.md) <!-- id:02-agents-01-cleanup --> — 1.5h est
- [ ] [Remove agent handbook prompt](./02-agents/02-handbook.md) <!-- id:02-agents-02-handbook --> — 0.5h est

### Testing & Review Competencies (03-testing/)

- [ ] [Move competencies to code-review workflow, make testing static](./03-testing/01-to-static.md) <!-- id:03-testing-01-to-static --> — 2h est
- [ ] [Add coverage step to develop workflow, remove testing guides](./03-testing/02-coverage-step.md) <!-- id:03-testing-02-coverage-step --> — 2h est

### Commands to Skills (04-commands/)

- [ ] [Migrate commands to skills](./04-commands/01-migrate.md) <!-- id:04-commands-01-migrate --> — 2h est

### Finalize (05-finalize/)

- [ ] [Update indexes, prompts, manifest, hashes](./05-finalize/01-indexes.md) <!-- id:05-finalize-01-indexes --> — 2h est
