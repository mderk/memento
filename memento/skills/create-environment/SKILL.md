---
name: create-environment
description: Generate a comprehensive AI-friendly development environment for your project
version: 3.0.0
---

# Create Environment Skill

Generate Memory Bank documentation for a project using the workflow engine. Supports three strategies: Fresh (clean generation), Resume (missing files only), Regenerate with merge (preserve local changes).

## Invocation

Before starting the relay loop, load the relay protocol by invoking the Skill tool with `skill: "memento-workflow:workflow-engine"`.

Then call `mcp__memento-workflow__start` with:
- workflow: `create-environment`
- variables: `{"plugin_root": "${CLAUDE_PLUGIN_ROOT}", "plugin_version": "1.6.0"}`
- cwd: `.`
- workflow_dirs: `["${CLAUDE_PLUGIN_ROOT}/skills/create-environment"]`

Follow the relay protocol to execute each returned action and call `mcp__memento-workflow__submit` with the result until the workflow completes.

## Workflow Phases

### Phase 0: Check Existing Environment

- Detect if `.memory_bank/` exists, count modified files
- If existing: prompt for strategy (Resume / Merge / Fresh)
- If new: proceed directly to Phase 1

### Phase 1: Detect & Plan

- Create `.memory_bank/` directory
- Run tech stack detection → `project-analysis.json`
- Build generation plan (evaluate prompt conditionals + manifest) → `generation-plan.md`
- Confirm plan with user

### Phase 2: Execute Strategy

**Fresh** (default): Copy static files, parallel-generate all prompt-based files, update plan

**Resume**: Load existing plan, generate only missing files in parallel

**Merge**: Copy statics with 3-way merge, sequential generate + merge per file, update plan

### Phase 3: Finalize

- Fix broken links (`fix-broken-links` skill)
- Check redundancy (`check-redundancy` skill)
- Create generation commits (`analyze-local-changes commit-generation`)

## Required Variables

| Variable         | Description                        |
| ---------------- | ---------------------------------- |
| `plugin_root`    | Absolute path to memento plugin    |
| `plugin_version` | Plugin version for commit metadata |

## File Access

During generation, Claude Code requests permission to read plugin files. Pre-approve with `Read(~/.claude/plugins/**)` in `.claude/settings.json`.
