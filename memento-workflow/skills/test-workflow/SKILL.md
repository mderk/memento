---
name: test-workflow
description: Interactive tour of engine capabilities — demonstrates all 9 block types
version: 3.0.0
model: sonnet
---

# Test Workflow Skill

Run the `test-workflow` workflow via the `memento-workflow` MCP server.

Call `mcp__plugin_memento-workflow_memento-workflow__start` with:

- workflow: `test-workflow`
- variables: `{}`
- cwd: `.`
- workflow_dirs: `["${CLAUDE_PLUGIN_ROOT}/skills/test-workflow", "${CLAUDE_PLUGIN_ROOT}/skills/test-workflow/sub-workflows"]`

Before starting the relay loop, load the relay protocol by invoking the Skill tool with `skill: "memento-workflow:workflow-engine"`. Then follow the relay protocol to execute each returned action and call `mcp__plugin_memento-workflow_memento-workflow__submit` with the result until the workflow completes.
