---
name: create-protocol
description: Create a protocol structure from a PRD with mini-ADR plan and step files
argument-hint: [protocol-number (optional), prd-file-name, additional-context]
version: 1.0.0
---

# Create Protocol

Generate a structured protocol from a PRD or task description using the workflow engine.

## Instructions

### 1. Resolve inputs

The user may specify the source in different ways:

- **Protocol number** (`3`, `003`): find `.protocols/003-*/prd.md`
- **Protocol path** (`.protocols/003-feature`): check for `prd.md` inside
- **PRD file path** (`path/to/prd.md`): use directly, create protocol dir
- **Task description** ("build admin dashboard"): will generate prd.md from description

Determine:
- `protocol_dir`: the `.protocols/NNNN-feature-name/` directory
- `prd_source`: set to task description text if no prd.md exists yet; empty if prd.md already exists

If no protocol directory exists, determine the next number:
```bash
ls .protocols/ 2>/dev/null | sort -r | head -1
```

### 2. Load workflow engine

Load the `memento-workflow:workflow-engine` skill (it contains the relay protocol you must follow).

### 3. Start the workflow

```
mcp__plugin_memento-workflow_memento-workflow__start(
  workflow="create-protocol",
  variables={
    "protocol_dir": "<resolved protocol directory>",
    "prd_source": "<task description or empty string>",
    "workdir": "<project root>"
  },
  cwd="<project root>"
)
```

### 4. Follow the relay protocol from the workflow-engine skill until the workflow completes.
