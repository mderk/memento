---
name: process-protocol
description: "Process and implement tasks from a protocol in git worktrees (or inline on the main workdir)"
argument-hint: [protocol number, path, or description] [--no-worktree]
version: 1.1.0
---

# Process Protocol

Run the **process-protocol** workflow to implement protocol steps.

Two modes:
- **Worktree (default)**: each protocol runs in an isolated `.worktrees/protocol-NNN` checkout. Allows parallel protocols, keeps main workdir clean.
- **Inline (`--no-worktree`)**: reuses the main workdir on branch `protocol-NNN`. Useful when tests need the main workdir, or when only one protocol runs at a time.

## Instructions

### 1. Resolve protocol directory

The user may specify a protocol in different ways. Resolve to a directory containing `plan.md`:

- **By number** (`3`, `003`): find matching directory in `.protocols/` (e.g., `.protocols/003-*`)
- **By path** (`.protocols/003-feature`): use directly
- **By description** ("the auth protocol"): list `.protocols/*/plan.md`, match by content
- **No argument**: infer from conversation context. If ambiguous, ask the user to clarify

Verify the resolved directory contains `plan.md` before proceeding.

### 2. Parse flags

If the user passes `--no-worktree` (anywhere in the arguments), set `no_worktree=true` in the variables block below. Otherwise omit it.

**Inline-mode preconditions** (when `--no-worktree` is used): the working directory must have no uncommitted changes. The workflow aborts early with a clear error if `git status --porcelain` is non-empty. Tell the user to commit or stash first.

### 3. Check for resumable run

Check if `<protocol_dir>/.last_run` exists. If it does:
- Read the run_id from the file
- Ask the user: **"Found a previous run (`<run_id>`). Resume it or start fresh?"**
- If resume: use the run_id in step 4
- If fresh: proceed without resume

### 4. Start workflow

Load the `memento-workflow:workflow-engine` skill, then:

**Fresh start (worktree mode):**
```
mcp__plugin_memento-workflow_memento-workflow__start(
  workflow="process-protocol",
  variables={"protocol_dir": "<resolved protocol directory>"},
  cwd="<project root>"
)
```

**Fresh start (inline mode):**
```
mcp__plugin_memento-workflow_memento-workflow__start(
  workflow="process-protocol",
  variables={"protocol_dir": "<resolved protocol directory>", "no_worktree": true},
  cwd="<project root>"
)
```

**Resume:** add `resume="<run_id from .last_run>"` to the call. Include the same `no_worktree` value the original run used.

### 5. Follow the relay protocol from the workflow-engine skill until the workflow completes.

### Finalization

- **Worktree mode**: run `/merge-protocol` to merge `.worktrees/protocol-NNN` back into develop.
- **Inline mode**: the branch `protocol-NNN` is committed in the main workdir. Merge manually when ready:
  ```
  git checkout develop && git merge --no-ff protocol-NNN
  ```
  `/merge-protocol` currently expects the worktree layout and does **not** support inline mode yet.
