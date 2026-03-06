---
name: load-context
description: Load shared context files for a protocol step. Use during process-protocol execution to gather relevant context before working on a step.
version: 1.0.0
---

# Load Context Skill

Load shared `_context/` files scoped to the current step's location.

## Usage

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/load-context/scripts/load-context.py <protocol-dir> <step-path>
```

The script reads all `.md` files from applicable `_context/` folders (group + protocol-wide) and outputs concatenated content. Per-step context belongs inline in the step file's `## Context` section.
