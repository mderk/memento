---
description: Execute a development task following the development workflow
---

# Develop

Run the full **development workflow** in standalone mode for a given task.

## Usage

```
/develop <task description>
```

## What it Does

Executes the [Development Workflow](./.memory_bank/workflows/development-workflow.md) in **standalone mode** (all phases):

1. **Phase 0**: Classify task, read relevant Memory Bank sections
2. **Phase 1**: Explore codebase with `@Explore` sub-agent
3. **Phase 2**: Create implementation plan with TodoWrite
4. **Phase 3**: Implement via `@Developer` sub-agent (per task unit)
5. **Phase 4**: Run `/code-review` for quality checks
6. **Phase 5**: Report completion, update Memory Bank

## Examples

```
/develop Add validation to the user registration form
/develop Fix the pagination bug in the products list
/develop Implement the new discount calculation logic
```

## Protocol Mode

This command runs **standalone mode** only. For protocol mode (pre-defined task lists, skip review/report), the `process-protocol` workflow invokes the development workflow directly — it does not use `/develop`.
