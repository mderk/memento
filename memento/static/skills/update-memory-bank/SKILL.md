---
name: update-memory-bank
description: Update Memory Bank documentation after code changes or protocol completion
argument-hint: [protocol-path (optional)]
---

# Update Memory Bank

## Instructions

1. Parse arguments:
   - `/update-memory-bank` → standard update (changes since last update)
   - `/update-memory-bank <protocol-path>` → post-protocol update (collect findings from step files)
2. Follow the workflow at `.claude/skills/update-memory-bank/workflow.md`
   - For standard updates: follow the standard Process (Steps 1-6)
   - For post-protocol: follow the "After Protocol Completion" section
