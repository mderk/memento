# Create Implementation Plan

You are creating a structured implementation plan based on task classification and codebase exploration.

## Task

{{variables.task}}

## Classification

{{results.classify}}

## Exploration Results

{{results.explore}}

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
