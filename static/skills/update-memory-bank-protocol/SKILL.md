---
name: update-memory-bank-protocol
description: Collect findings from a completed protocol and update Memory Bank documentation
argument-hint: <protocol-path>
context: fork
disable-model-invocation: true
---

# Update Memory Bank from Protocol Findings

Protocol path: `$ARGUMENTS`

## Instructions

1. Read `.memory_bank/workflows/update-memory-bank.md`
2. Execute the **"After Protocol Completion"** section (steps 1–5) for the protocol at the given path
3. Follow the **"What NOT to Update"** and **"Check Existing Content"** rules from the same file when applying changes

## Output

Report what was updated:

```
Memory Bank Updated
─────────────────────────
Protocol: {name}

Findings collected: N
After triage: M
Files updated: K

Changes:
  - guides/backend.md: added section on X
  - tech_stack.md: updated Y dependency

Discarded: N findings (task-specific / already documented / temporary)
```
