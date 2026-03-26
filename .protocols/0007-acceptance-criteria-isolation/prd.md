# Acceptance Criteria + Evaluator Isolation — Requirements

## Problem Statement

The develop workflow suffers from self-evaluation bias: acceptance check runs in the same context as implementation, extracts its own requirements on the fly, and has escape hatches (out_of_scope) that allow rationalizing gaps. Write-tests sees implementation context (anti-TDD). PlanTask predicts files/test_files that aren't used downstream but may mislead.

## Requirements

- Add acceptance_criteria field to PlanTask schema; plan prompt generates 2-5 concrete criteria per task
- Parse <!-- accept --> sections in protocol step files into unit acceptance_criteria via helpers.py
- Simplify AcceptanceOutput: remove requirements and out_of_scope fields, keep covered/missing/passed
- Rewrite acceptance check prompt to verify against provided criteria instead of extracting own; fallback to extraction if criteria empty
- Run acceptance check as isolation=subagent — receives only criteria + workdir, no implementation context
- Run write-tests as isolation=subagent — writes tests from spec, not from explore/plan context
- Add WriteTestsOutput schema; write-tests returns list of created test files
- Wire verify-red to read files from write-tests result instead of unit.test_files
- Remove files and test_files from PlanTask schema; planner focuses on description + acceptance_criteria

## Constraints

- Existing workflow tests must pass after changes
- Fallback behavior for old step files without <!-- accept --> blocks
- Protocol mode and normal mode must use the same unit format
- Source hashes must be recomputed after static file changes

## Acceptance Criteria

- Protocol step files with <!-- accept --> blocks produce units with populated acceptance_criteria
- Plan step generates acceptance_criteria for each PlanTask in normal mode
- Acceptance check subagent verifies against provided criteria without access to implementation context
- Write-tests subagent produces tests from unit spec without explore/plan context leaking
- Verify-red runs test files returned by write-tests, not predicted by plan
- AcceptanceOutput has no requirements or out_of_scope fields
- Old step files without <!-- accept --> blocks still work via fallback extraction

## Source

Generated from task description: 2026-03-25
