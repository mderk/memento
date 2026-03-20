---
id: 06-update-relay-protocol-and-run-integration-test
status: done
estimate: 1h
---
# Update relay protocol and run integration test

## Objective

<!-- objective -->
Update the relay protocol SKILL.md with all new fields and verify the complete optimization works end-to-end with the test-workflow.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Consolidate relay protocol updates

- [ ] Update SKILL.md prompt handler with prompt_file and schema_file
  Document the new flow:
  1. If `prompt_file` is present → Read the file for full prompt text
  2. If `schema_file` is present → Read the file for JSON schema
  3. Fallback to inline `prompt` and `json_schema` fields

- [ ] Update SKILL.md parallel handler with shared_prompt

- [ ] Update SKILL.md completed handler with compact note
<!-- /task -->

<!-- task -->
### Run end-to-end integration test

- [ ] Run test-workflow with all optimizations enabled
  Execute `/memento-workflow:test-workflow` and verify all steps complete successfully with the updated relay protocol.

- [ ] Run commit workflow to verify backward compatibility

- [ ] Verify tests pass across the full suite
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- All existing workflows must work without modification
- SKILL.md must document both new and old behavior
- Integration test must complete successfully
<!-- /constraints -->

## Implementation Notes

The relay protocol SKILL.md may have been partially updated in earlier steps. This step consolidates all changes and ensures consistency. The integration test is the final verification that everything works together.

## Verification

<!-- verification -->
```bash
cd memento-workflow && uv run pytest tests/ -x -q
cd memento-workflow && uv run ruff check scripts/
cd memento-workflow && uv run pyright scripts/
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento-workflow/skills/workflow-engine/SKILL.md
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] .memory_bank/tech_stack.md
