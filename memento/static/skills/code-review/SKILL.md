---
name: code-review
description: Run structured code review with parallel competency-based analysis
argument-hint: [branch or commit range]
version: 1.0.0
---

# Code Review

Run the **code-review** workflow for multi-competency review.

## Instructions

1. Load the `memento-workflow:workflow-engine` skill (it contains the relay protocol you must follow).
2. Start the workflow:

```
mcp__plugin_memento-workflow_memento-workflow__start(
  workflow="code-review",
  variables={"scope": "<branch, commit range, or empty string for uncommitted changes>"},
  cwd="<project root>"
)
```

If the user provides a branch or commit range (e.g., `main..HEAD`, `HEAD~3`), pass it as `scope`. Otherwise pass an empty string for default (uncommitted + staged changes).

3. Follow the relay protocol from the workflow-engine skill until the workflow completes.
