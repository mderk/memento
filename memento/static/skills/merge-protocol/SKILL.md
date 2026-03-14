---
name: merge-protocol
description: Merge a protocol branch into develop with code review
argument-hint: [protocol number, path, or description]
version: 1.0.0
---

# Merge Protocol

Run the **merge-protocol** workflow to merge a completed protocol branch into develop.

## Instructions

### 1. Resolve protocol directory

The user may specify a protocol in different ways. Resolve to a directory containing `plan.md`:

- **By number** (`3`, `003`): find matching directory in `.protocols/` (e.g., `.protocols/003-*`)
- **By path** (`.protocols/003-feature`): use directly
- **By description** ("the auth protocol"): list `.protocols/*/plan.md`, match by content
- **No argument**: infer from conversation context. If ambiguous, ask the user to clarify

Verify the resolved directory contains `plan.md` before proceeding.

### 2. Start workflow

Load the `memento-workflow:workflow-engine` skill, then:

```
mcp__plugin_memento-workflow_memento-workflow__start(
  workflow="merge-protocol",
  variables={"protocol_dir": "<resolved protocol directory>"},
  cwd="<project root>"
)
```

### 3. Follow the relay protocol from the workflow-engine skill until the workflow completes.
