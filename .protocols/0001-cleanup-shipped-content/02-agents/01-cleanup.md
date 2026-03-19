---
id: 02-agents-01-cleanup
status: done
estimate: 1.5h
---

# Remove agent-orchestration and Convert Agents to Skills

## Objective

<!-- objective -->
Remove the unused agent-orchestration workflow, convert the two custom agent files (design-reviewer, research-analyst) to skills with fork model, and clean up all references.
<!-- /objective -->

## Tasks

<!-- tasks -->
- [ ] Delete `memento/static/memory_bank/workflows/agent-orchestration.md`
- [ ] Remove agent-orchestration.md entry from `memento/static/manifest.yaml`
- [ ] Convert `memento/static/agents/design-reviewer.md` → `memento/static/skills/design-reviewer/SKILL.md`
  - Reformat from agent YAML frontmatter to skill YAML frontmatter
  - Add `model: fork` (or equivalent for subagent isolation)
  - Keep the review instructions and process
  - Remove "Automatic Execution" section (proactive invocation doesn't apply to skills)
- [ ] Convert `memento/static/agents/research-analyst.md` → `memento/static/skills/research-analyst/SKILL.md`
  - Same conversion as design-reviewer
- [ ] Delete `memento/static/agents/design-reviewer.md` and `memento/static/agents/research-analyst.md`
- [ ] Update `memento/static/manifest.yaml`:
  - Remove old agent entries (agents/design-reviewer.md, agents/research-analyst.md)
  - Add new skill entries (skills/design-reviewer/SKILL.md, skills/research-analyst/SKILL.md) with same conditionals
- [ ] Grep for references to `agents/design-reviewer` and `agents/research-analyst` in all static/ and prompts/ files — update paths
- [ ] Remove references to @Developer agent from all shipped content (it doesn't exist as a file)
<!-- /tasks -->

## Constraints

<!-- constraints -->
- design-reviewer skill must keep conditional: `has_frontend`
- research-analyst skill has no conditional (always deployed)
- Skill frontmatter format must match existing skills (commit, defer, etc.)
- No functional behavior change — same review/research capabilities, just different invocation mechanism
<!-- /constraints -->

## Implementation Notes

Agent → Skill frontmatter mapping:

```yaml
# Agent format:
---
name: design-reviewer
description: "..."
tools: Bash, Glob, Grep, Read, WebFetch, WebSearch
model: sonnet
color: green
---

# Skill format:
---
name: design-reviewer
description: "..."
model: fork
---
```

Key difference: skills don't specify tools (they inherit from the parent) or color. The `model: fork` gives process isolation similar to an agent.

After this step, `memento/static/agents/` directory should be empty and can be removed.

## Verification

<!-- verification -->
```bash
# Verify agent files are gone
test ! -f memento/static/agents/design-reviewer.md && test ! -f memento/static/agents/research-analyst.md && echo "Agent files removed"
# Verify skill files exist
test -f memento/static/skills/design-reviewer/SKILL.md && test -f memento/static/skills/research-analyst/SKILL.md && echo "Skill files created"
# Verify no references to old agent paths in manifest
grep -c 'agents/' memento/static/manifest.yaml | grep '^0$' && echo "No agent entries in manifest"
# Verify no @Developer references in shipped content
grep -r '@Developer' memento/static/ memento/prompts/ | grep -v '.pyc' || echo "No @Developer references"
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento/static/agents/design-reviewer.md
- memento/static/agents/research-analyst.md
- memento/static/memory_bank/workflows/agent-orchestration.md
- memento/static/manifest.yaml
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
