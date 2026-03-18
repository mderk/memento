---
id: 02-agents-02-handbook
status: pending
estimate: 0.5h
---

# Remove Agent Handbook Prompt

## Objective

<!-- objective -->
Delete the `ai-agent-handbook.md` prompt entirely. It is not read by any process during real work: `/prime` doesn't load it, the workflow engine handles orchestration, severity levels are defined inline in each review competency, and the README already serves as the tools catalog.
<!-- /objective -->

## Tasks

<!-- tasks -->
- [ ] Delete `memento/prompts/memory_bank/guides/ai-agent-handbook.md.prompt`
- [ ] Remove references to `ai-agent-handbook.md` in other shipped files:
  - `prompts/memory_bank/README.md.prompt` — remove from Guides table
  - `static/memory_bank/workflows/index.md` — remove from Related Documentation
  - Any other files found via grep
- [ ] Verify `{{SEVERITY_LEVELS}}` template variable in `prompts/templates/reusable-blocks.md` is not left orphaned — if no other prompt uses it, remove the block too
<!-- /tasks -->

## Constraints

<!-- constraints -->
- Review competencies define severity levels inline — no need to relocate `{{SEVERITY_LEVELS}}`
- README.md prompt must be updated to remove the guide entry
<!-- /constraints -->

## Implementation Notes

The `{{SEVERITY_LEVELS}}` template variable is defined in `prompts/templates/reusable-blocks.md` and was only consumed by the handbook prompt. Review competencies (architecture.md, security.md, etc.) each define their own severity sections. Removing the template block is safe.

## Verification

<!-- verification -->
```bash
# Verify prompt is gone
test ! -f memento/prompts/memory_bank/guides/ai-agent-handbook.md.prompt && echo "Handbook prompt removed"
# Verify no broken references
grep -r 'ai-agent-handbook' memento/static/ memento/prompts/ | grep -v '.pyc' || echo "No references to handbook"
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento/prompts/memory_bank/guides/ai-agent-handbook.md.prompt
- memento/prompts/templates/reusable-blocks.md
- memento/prompts/memory_bank/README.md.prompt
- memento/static/memory_bank/workflows/index.md
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
