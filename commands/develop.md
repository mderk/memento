---
description: Execute a development task using the developer sub-agent
---

# Develop

Invoke the `@developer` agent to execute a development task following the development workflow.

## Usage

```
/develop <task description>
```

## What it Does

1. Launches the `@developer` sub-agent (model: sonnet)
2. The agent reads `.memory_bank/workflows/development-workflow.md`
3. Executes the task following the workflow exactly
4. Returns results and lessons learned

## Examples

```
/develop Add validation to the user registration form
/develop Fix the pagination bug in the products list
/develop Implement the new discount calculation logic
```

## Integration with Protocol Workflow

This command is used by `process-protocol` to delegate subtasks to the developer agent, maintaining separation between orchestration (main agent) and execution (sub-agent).

## Agent Reference

See `agents/developer.md` for the agent definition.
