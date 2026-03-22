# Fill Coverage Gaps

You are writing additional tests to close coverage gaps on changed files.

## Coverage Report

{{variables.coverage}}

## Working Directory

All file writes and edits must target `{{variables.workdir}}`.

## Instructions

1. Read the coverage report above — it lists changed files with less than 100% line coverage and their uncovered lines
2. For each file with coverage gaps:
   - Read the source file to understand what the uncovered lines do
   - Read existing test files for that module
   - Write tests that exercise the uncovered lines/branches
3. Focus on:
   - Uncovered error paths and edge cases
   - Uncovered branches in conditionals
   - Uncovered exception handlers
4. Write ONLY test files. Do NOT modify production code.

## Constraints

- Do NOT run tests — the workflow runs them automatically in the next step
- Do not modify existing test assertions
- Follow existing test file organization and patterns
- Focus on uncovered lines from the report, not general improvements
