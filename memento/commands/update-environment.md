---
description: Update Memory Bank files after tech stack changes or plugin updates with smart detection
---

# Update Environment

Run the `update-environment` workflow via the `memento-workflow` MCP server.

First, load the relay protocol by invoking the Skill tool with `skill: "memento-workflow:workflow-engine"`.

Then call `mcp__memento-workflow__start` with:
- workflow: `update-environment`
- variables: `{"plugin_root": "${CLAUDE_PLUGIN_ROOT}", "plugin_version": "1.6.0"}`
- cwd: `.`
- workflow_dirs: `["${CLAUDE_PLUGIN_ROOT}/skills/update-environment"]`

Follow the relay protocol to execute each returned action and call `mcp__memento-workflow__submit` with the result until the workflow completes.

See `${CLAUDE_PLUGIN_ROOT}/skills/update-environment/SKILL.md` for workflow phase details.
