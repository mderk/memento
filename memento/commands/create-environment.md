---
description: Generate a comprehensive AI-friendly development environment for your project
---

# Create Environment

Run the `create-environment` workflow via the `memento-workflow` MCP server.

First, load the relay protocol by invoking the Skill tool with `skill: "memento-workflow:workflow-engine"`.

Then call `mcp__memento-workflow__start` with:
- workflow: `create-environment`
- variables: `{"plugin_root": "${CLAUDE_PLUGIN_ROOT}", "plugin_version": "1.6.0"}`
- cwd: `.`
- workflow_dirs: `["${CLAUDE_PLUGIN_ROOT}/skills/create-environment"]`

Follow the relay protocol to execute each returned action and call `mcp__memento-workflow__submit` with the result until the workflow completes.

See `${CLAUDE_PLUGIN_ROOT}/skills/create-environment/SKILL.md` for workflow phase details.
