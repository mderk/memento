---
name: test-workflow
description: Comprehensive engine test exercising all 9 block types
version: 2.0.0
model: haiku
---

# Test Workflow Skill

Your task: run the bash command below, then handle its output.

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/workflow-engine/run.py test-workflow \
  --workflow-dir ${CLAUDE_PLUGIN_ROOT}/skills/test-workflow \
  --workflow-dir ${CLAUDE_PLUGIN_ROOT}/skills/test-workflow/sub-workflows \
  --cwd . \
  --output .workflow-state/output.txt; cat .workflow-state/output.txt
```

If the output contains a `workflow_question` JSON block, follow the INSTRUCTION printed after it. Otherwise, print the results summary.
