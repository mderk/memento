---
id: 03-testing-02-coverage-step
status: pending
estimate: 2h
---

# Add Coverage Step to Develop Workflow and Remove Testing Guides

## Objective

<!-- objective -->
Add a coverage-check step to the develop workflow that verifies 100% line coverage on changed files and writes gap-filling tests. Embed the actionable testing rules from guides into the develop workflow prompts. Remove the three testing guide prompts (testing.md, testing-backend.md, testing-frontend.md) since their useful content now lives where it's actually used.
<!-- /objective -->

## Tasks

<!-- tasks -->
### Coverage step in develop workflow

- [ ] Add `dev-tools.py` command: `coverage` — runs tests with coverage, returns per-file coverage report for changed files (JSON: `{file: path, covered: N, total: N, missing_lines: [...]}`)
- [ ] Create prompt `03d-coverage.md`:
  - Receives coverage report from shell step
  - Analyzes uncovered lines/branches in changed files
  - Writes additional tests to cover gaps
  - Includes test quality rules (see "Rules to embed" below)
  - Does NOT run tests — next step does that
- [ ] Add blocks to `workflow.py` after TDD loop, before acceptance-check:
  ```python
  # Coverage: initial check
  ShellStep(
      name="coverage-check",
      script=_TOOLS,
      args="coverage --workdir {{variables.workdir}}",
      result_var="coverage",
      condition=lambda ctx: not ctx.result_field("classify", "fast_track"),
  ),
  # Coverage: retry loop until gaps closed
  RetryBlock(
      name="coverage-retry",
      condition=lambda ctx: (
          not ctx.result_field("classify", "fast_track")
          and ctx.variables.get("coverage", {}).get("has_gaps", False)
      ),
      until=lambda ctx: not ctx.variables.get("coverage", {}).get("has_gaps", False),
      max_attempts=3,
      blocks=[
          LLMStep(
              name="coverage-fill",
              prompt="03d-coverage.md",
              tools=["Read", "Write", "Edit", "Glob", "Grep"],
          ),
          SubWorkflow(
              name="verify-after-coverage",
              workflow="verify-fix",
              inject={"workdir": "{{variables.workdir}}", "scope": "{{results.classify.structured_output.scope}}"},
          ),
          ShellStep(
              name="re-coverage-check",
              script=_TOOLS,
              args="coverage --workdir {{variables.workdir}}",
              result_var="coverage",
          ),
      ],
  ),
  ```
- [ ] The coverage step should be skipped for fast_track (trivial changes) and for refactors with no behavior change

### Embed test quality rules

- [ ] Add "Test Quality Rules" block to `03a-write-tests.md` — this is the first test-writing prompt in the workflow, rules stay in LLM context for all subsequent test-writing steps (`03d-coverage`, `03h-acceptance-tests`):
  ```markdown
  ## Test Quality Rules
  - Assert behavior, not implementation (no checking internal call order)
  - Mock at boundaries (external APIs, DB), not internal helpers
  - No bare sleeps — use framework waits/polling
  - Assert contract (response body, side effects), not just status codes
  - One assertion concern per test — clear failure messages
  ```
- [ ] `03d-coverage.md` does NOT repeat these rules — they are already in context from `03a`. Coverage prompt focuses on: reading coverage report, identifying gaps, writing tests for uncovered lines.

### Remove testing guides

- [ ] Delete `memento/prompts/memory_bank/guides/testing.md.prompt`
- [ ] Delete `memento/prompts/memory_bank/guides/testing-backend.md.prompt`
- [ ] Delete `memento/prompts/memory_bank/guides/testing-frontend.md.prompt`
- [ ] Remove references to testing guides in other prompts:
  - `README.md.prompt` — remove from Guides table
  - `code-review-guidelines.md.prompt` — update references
  - Any other files via grep
- [ ] Note: `review/testing.md` (review competency) is NOT removed — it's handled in step 03-testing/01-to-static
<!-- /tasks -->

## Constraints

<!-- constraints -->
- Coverage step must work with whatever test framework the project uses (dev-tools.py handles detection)
- Coverage step is skipped for fast_track tasks
- The LLM step only runs if there are actual coverage gaps (`has_gaps == True`)
- Test quality rules added once in `03a-write-tests.md` — carried in LLM context to 03d and 03h, no duplication
<!-- /constraints -->

## Implementation Notes

### Where in workflow.py

The new blocks go after `verify-custom-retry` and before `acceptance-check`:

```python
# ... verify-custom-retry block ...

# --- NEW: Coverage ---
ShellStep(name="coverage-check", ...),       # initial check
RetryBlock(name="coverage-retry", ...),      # fill gaps → verify → re-check, up to 3×

# --- Existing: Acceptance ---
LLMStep(name="acceptance-check", ...),
```

### dev-tools.py `coverage` command

Should:
1. Detect changed files via `git diff --name-only` (against base branch or HEAD~N)
2. Run test suite with coverage (pytest-cov / c8 / coverage.py / etc.)
3. Parse coverage report for changed files only
4. Return structured JSON:
```json
{
  "has_gaps": true,
  "overall_coverage": 87.5,
  "files": [
    {"path": "src/auth/service.py", "coverage": 72, "missing_lines": [45, 46, 78, 82]},
    {"path": "src/auth/middleware.py", "coverage": 100, "missing_lines": []}
  ]
}
```

### Test quality rules — single source, no duplication

All test-writing steps (`03a`, `03d`, `03h`) run in one LLM context. Rules are stated once in `03a-write-tests.md` (the first test-writing prompt) and carry forward through the conversation. No shared files, no shell injection, no repetition.

`review/testing.md` (review competency) has its own rules — that's a different context (code-review subagent), so overlap with 03a is fine.

### What testing guides contained

Non-actionable content (philosophy, pyramid explanation, TDD explanation, debugging tips) is **dropped** — the workflow structure itself embodies TDD, and the model knows debugging. The actionable rules move into `03a-write-tests.md`.

## Verification

<!-- verification -->
```bash
# Verify new prompt exists
test -f memento/static/workflows/develop/prompts/03d-coverage.md && echo "Coverage prompt exists"
# Verify testing guides removed
test ! -f memento/prompts/memory_bank/guides/testing.md.prompt && echo "testing.md.prompt removed"
test ! -f memento/prompts/memory_bank/guides/testing-backend.md.prompt && echo "testing-backend.md.prompt removed"
test ! -f memento/prompts/memory_bank/guides/testing-frontend.md.prompt && echo "testing-frontend.md.prompt removed"
# Verify workflow.py has coverage step
grep 'coverage-check' memento/static/workflows/develop/workflow.py && echo "Coverage step in workflow"
# Run tests
uv run pytest
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento/static/workflows/develop/workflow.py
- memento/static/workflows/develop/prompts/03a-write-tests.md
- memento/static/workflows/develop/dev-tools.py
- memento/prompts/memory_bank/guides/testing.md.prompt
- memento/prompts/memory_bank/guides/testing-backend.md.prompt
- memento/prompts/memory_bank/guides/testing-frontend.md.prompt
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected (guides removed, content moved to workflow prompts)
