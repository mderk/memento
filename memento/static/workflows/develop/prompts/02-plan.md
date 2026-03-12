# Create Implementation Plan

You are creating a structured implementation plan based on task classification and codebase exploration.

Use the task and classification from the earlier steps in this conversation.

## Exploration Results

{{results.explore.structured_output}}

## Instructions

1. Break the task into minimal, independently testable units of work
2. Each task should have:
   - A short ID (e.g. "add-model", "update-api", "add-tests")
   - A clear description of what to implement
   - List of files to create or modify
   - List of test files to create or modify
   - Dependencies on other tasks (by ID)
3. Order tasks by dependency (implement dependencies first)
4. For bug fixes: first task should be "write reproducing test"
5. For features: group by logical component

## Output

Respond with a JSON object matching the output schema with the ordered list of tasks.

Include any **findings** (tag: DECISION, GOTCHA, or REUSE) discovered during planning — architectural choices, gotchas, or reusable patterns worth recording.
