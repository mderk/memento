---
name: update-environment
description: Update Memory Bank files after tech stack changes or plugin updates with smart detection
version: 3.0.0
---

# Update Environment Skill

Selective update/regeneration of Memory Bank files with smart change detection. Detects tech stack changes, plugin updates, local modifications, and applies 3-way merge to preserve user edits.

## Invocation

Before starting the relay loop, load the relay protocol by invoking the Skill tool with `skill: "memento-workflow:workflow-engine"`.

Then call `mcp__memento-workflow__start` with:
- workflow: `update-environment`
- variables: `{"plugin_root": "${CLAUDE_PLUGIN_ROOT}", "plugin_version": "1.6.0"}`
- cwd: `.`
- workflow_dirs: `["${CLAUDE_PLUGIN_ROOT}/skills/update-environment"]`

Follow the relay protocol to execute each returned action and call `mcp__memento-workflow__submit` with the result until the workflow completes.

## Workflow Phases

### Phase 0: Detect Changes

- Re-detect tech stack → `/tmp/new-project-analysis.json`
- Run pre-update check (`analyze-local-changes pre-update`)
  - Local file modifications (hash comparison)
  - Plugin source changes (prompt/static updates)
  - New/removed prompt files
  - Static file classification (new/safe_overwrite/local_only/merge_needed/up_to_date)
  - Obsolete file detection
  - Tech stack diff with impact classification
- Present recommendations to user
- User selects action (affected files / new prompts / static files / delete obsolete / all / full regen)

### Phase 1: Execute Update

**Static files**: Copy via `analyze-local-changes copy-static` with 3-way merge

**Prompt-based files**: Regenerate in batches with merge support

**Obsolete files**: Remove from project and generation plan

**New prompts**: Generate missing files

### Phase 2: Finalize

- Update generation plan with hashes
- Fix broken links (validate regenerated files)
- Create generation commits (base + merge)
- Verify merge results

## Required Variables

| Variable         | Description                        |
| ---------------- | ---------------------------------- |
| `plugin_root`    | Absolute path to memento plugin    |
| `plugin_version` | Plugin version for commit metadata |
