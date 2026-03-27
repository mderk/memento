---
name: process-protocol
description: Process and implement tasks from a protocol in git worktrees
argument-hint: [protocol number, path, or description]
version: 1.0.0
---

# Process Protocol

Run the **process-protocol** workflow to implement protocol steps in isolated git worktrees.

## Instructions

### 1. Resolve protocol directory

The user may specify a protocol in different ways. Resolve to a directory containing `plan.md`:

- **By number** (`3`, `003`): find matching directory in `.protocols/` (e.g., `.protocols/003-*`)
- **By path** (`.protocols/003-feature`): use directly
- **By description** ("the auth protocol"): list `.protocols/*/plan.md`, match by content
- **No argument**: infer from conversation context. If ambiguous, ask the user to clarify

Verify the resolved directory contains `plan.md` before proceeding.

### 2. Check for resumable run

Check if `<protocol_dir>/.last_run` exists. If it does:
- Read the run_id from the file
- Ask the user: **"Found a previous run (`<run_id>`). Resume it or start fresh?"**
- If resume: use the run_id in step 3
- If fresh: proceed without resume

### 3. Start workflow

Load the `memento-workflow:workflow-engine` skill, then:

**Fresh start:**
```
mcp__plugin_memento-workflow_memento-workflow__start(
  workflow="process-protocol",
  variables={"protocol_dir": "<resolved protocol directory>"},
  cwd="<project root>"
)
```

**Resume:**
```
mcp__plugin_memento-workflow_memento-workflow__start(
  workflow="process-protocol",
  variables={"protocol_dir": "<resolved protocol directory>"},
  resume="<run_id from .last_run>",
  cwd="<project root>"
)
```

### 4. Follow the relay protocol from the workflow-engine skill until the workflow completes.
