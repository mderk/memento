---
name: run-tests
description: Run tests (optional coverage) using the testing workflow
argument-hint: [test files or description]
version: 1.0.2
---

# Run Tests

Run the **testing** workflow to execute tests. Coverage is **optional** (disabled by default).

## Instructions

1. Load the `memento-workflow:workflow-engine` skill (it contains the relay protocol you must follow).
2. Start the workflow:

```
mcp__plugin_memento-workflow_memento-workflow__start(
  workflow="testing",
  variables={"coverage": false, "test_scope": "all", "target": "all"},
  cwd="<project root>"
)
```

If the user explicitly asks for coverage, set `coverage` to true:

```
mcp__plugin_memento-workflow_memento-workflow__start(
  workflow="testing",
  variables={"coverage": true, "test_scope": "all", "target": "all"},
  cwd="<project root>"
)
```

To run only changed tests:

```
mcp__plugin_memento-workflow_memento-workflow__start(
  workflow="testing",
  variables={"coverage": false, "test_scope": "changed", "target": "all"},
  cwd="<project root>"
)
```

To run specific tests, pass `test_files` as a JSON array:

```
mcp__plugin_memento-workflow_memento-workflow__start(
  workflow="testing",
  variables={"coverage": false, "test_scope": "specific", "target": "all", "test_files": ["tests/test_example.py"]},
  cwd="<project root>"
)
```

To run backend-only or frontend-only tests, set `target` to `backend` or `frontend`.

3. Follow the relay protocol from the workflow-engine skill until the workflow completes.
