---
name: run-tests
description: Run tests with coverage analysis using the testing workflow
argument-hint: [test files or description]
version: 1.0.0
---

# Run Tests

Run the **testing** workflow to execute tests with coverage analysis.

## Instructions

1. Load the `memento-workflow:workflow-engine` skill (it contains the relay protocol you must follow).
2. Start the workflow:

```
mcp__plugin_memento-workflow_memento-workflow__start(
  workflow="testing",
  variables={},
  cwd="<project root>"
)
```

The workflow auto-detects test scope from changed files. No variables are required.

3. Follow the relay protocol from the workflow-engine skill until the workflow completes.
