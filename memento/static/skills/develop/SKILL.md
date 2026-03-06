---
name: develop
description: Execute a development task following the TDD development workflow
argument-hint: <task description>
version: 1.0.0
---

# Develop

Run the **development** workflow for a given task.

## Instructions

1. Load the `memento-workflow:workflow-engine` skill (it contains the relay protocol you must follow).
2. Start the workflow:

```
mcp__plugin_memento-workflow_memento-workflow__start(
  workflow="development",
  variables={"task": "<user's task description>"},
  cwd="<project root>"
)
```

3. Follow the relay protocol from the workflow-engine skill until the workflow completes.
