# Explore Codebase

You are exploring the codebase to find relevant files, patterns, and tests for the current task.

## Task

{{variables.task}}

## Classification

{{results.classify.structured_output}}

## Instructions

Use the exploration strategy matching the task type from classification:

**Bug investigation:**
- Trace from symptom/error to root cause: entry point → failure point
- Find error handling, logging, related tests

**New feature:**
- Find existing implementation of similar features
- Identify patterns used, components involved, integration points

**Refactoring:**
- Find all usages of the target (function/component/module)
- Map what uses it, what it depends on, safe modification order

**General steps:**

1. Use Glob to find files related to the task area
2. Use Grep to search for relevant patterns, function names, and imports
3. Read key files to understand existing patterns and conventions
4. Identify:
   - Files that need modification
   - Files to use as reference (existing patterns to follow)
   - Existing tests that need updating or serve as examples
   - Integration points and dependencies

## Output

Respond with a JSON object matching the output schema:

- **files_to_modify**: files that need changes
- **reference_files**: files showing patterns to follow
- **existing_tests**: test files covering affected code
- **patterns**: coding patterns observed in the codebase
- **findings**: any discoveries worth noting (tag: DECISION, GOTCHA, or REUSE)
