---
description: Update Memory Bank from protocol Findings (post-completion)
argument-hint: <protocol-path>
---

# Rule: Update Memory Bank (After Protocol Completion)

Protocol path: `$ARGUMENTS`

Follow the workflow at **`.memory_bank/workflows/update-memory-bank.md`**, specifically the **"After Protocol Completion"** section.

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

