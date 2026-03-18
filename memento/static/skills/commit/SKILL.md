---
name: commit
description: Stage changes and create a git commit with a well-formatted message. Use when the user asks to commit, or when a workflow requires committing changes.
argument-hint: [amend] [instructions...]
version: 2.0.0
---

# Git Commit Skill

Stage changes and commit with messages that follow project conventions, powered by the workflow engine.

## Instructions

1. Load the `memento-workflow:workflow-engine` skill (it contains the relay protocol you must follow).
2. Parse the user's arguments:
   - `/commit` → `user_args: "", amend: "false"`
   - `/commit amend` → `user_args: "", amend: "true"`
   - `/commit amend fix typo` → `user_args: "fix typo", amend: "true"`
   - `/commit split by themes` → `user_args: "split by themes", amend: "false"`
   - `/commit only backend` → `user_args: "only backend", amend: "false"`
3. Start the workflow:

```
mcp__plugin_memento-workflow_memento-workflow__start(
  workflow="commit",
  variables={"user_args": "<parsed instructions>",
             "workdir": "<project root>",
             "amend": "<true|false>"},
  cwd="<project root>"
)
```

4. Follow the relay protocol from the workflow-engine skill until the workflow completes.
