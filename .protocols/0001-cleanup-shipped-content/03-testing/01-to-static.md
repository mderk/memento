---
id: 03-testing-01-to-static
status: pending
estimate: 2h
---

# Move Review Competencies to Code-Review Workflow, Make Testing Static

## Objective

<!-- objective -->
Move all review competency files from `.memory_bank/workflows/review/` to `.workflows/code-review/competencies/` (co-located with the workflow that uses them). Make the testing competency fully static (delete the prompt). Inject competency content into review prompts via ShellStep instead of LLM Read tool calls. Remove code-review-guidelines prompt (not used by any process).
<!-- /objective -->

## Tasks

<!-- tasks -->
### Move competency files

- [ ] Move all static competency files from `memento/static/memory_bank/workflows/review/` to `memento/static/workflows/code-review/competencies/`:
  - architecture.md, security.md, performance.md, data-integrity.md, simplicity.md, protocol-completeness.md
  - python.md (conditional: has_python)
  - typescript.md (conditional: has_typescript)
- [ ] Update all target paths in `memento/static/manifest.yaml`

### Create static testing competency

- [ ] Create `memento/static/workflows/code-review/competencies/testing.md`:
  - Universal rules only: Scope, Principles, 6 Rule groups, Anti-Patterns, Severity
  - No links to platform files (ShellStep handles concatenation)
  - Target: 70–90 lines
  - Conditional in manifest: `has_tests`
- [ ] Create `memento/static/workflows/code-review/competencies/testing-platforms/pytest.md`:
  - pytest + Django/FastAPI specifics (~20–30 lines, checklist format)
  - Conditional in manifest: `has_python`
- [ ] Create `memento/static/workflows/code-review/competencies/testing-platforms/jest.md`:
  - Jest/Vitest + React/Vue + Playwright/Cypress specifics (~25–35 lines)
  - Conditional in manifest: `has_typescript`
- [ ] Delete `memento/prompts/memory_bank/workflows/review/testing.md.prompt`

### Inject competency content via ShellStep

- [ ] Update `workflow.py` — replace the current ParallelEachBlock (which has only an LLMStep) with ShellStep + LLMStep:
  ```python
  ParallelEachBlock(
      name="reviews",
      parallel_for="results.scope.structured_output.competencies",
      template=[
          ShellStep(
              name="load-competency",
              command=(
                  "cat .workflows/code-review/competencies/{{variables.item}}.md "
                  ".workflows/code-review/competencies/{{variables.item}}-platforms/*.md "
                  "2>/dev/null"
              ),
              result_var="competency_rules",
          ),
          LLMStep(
              name="review",
              prompt="02-review.md",
              tools=["Read", "Grep", "Glob"],
              model="opus",
              output_schema=CompetencyReview,
          ),
      ],
  ),
  ```
  How it works:
  - For most competencies (architecture, security, etc.) — cats one file, glob returns nothing
  - For testing — cats `testing.md` + all deployed files from `testing-platforms/`
  - Manifest conditionals control which platform files exist on disk; ShellStep cats whatever is there
  - In fullstack projects, testing subagent gets both pytest.md and jest.md (~25 lines overhead, harmless)
- [ ] Update `02-review.md` prompt — remove "Read the competency rules from ..." instruction, replace with:
  ```markdown
  ## Competency Rules: {{variables.item}}

  {{variables.competency_rules}}
  ```
- [ ] Update `01-scope.md` — change `ls .memory_bank/workflows/review/` to `ls .workflows/code-review/competencies/`

### Remove code-review-guidelines.md prompt

- [ ] Delete `memento/prompts/memory_bank/guides/code-review-guidelines.md.prompt`
  - Severity definitions → already in `02-review.md` and each competency file
  - Review conduct → irrelevant (subagents return structured JSON)
  - Responding to feedback → human process, not used by AI
- [ ] Remove references to `code-review-guidelines.md` in other prompts (README.md.prompt, getting-started.md.prompt, etc.)

### Clean up old paths

- [ ] Remove old `memento/static/memory_bank/workflows/review/` directory
- [ ] Grep for `workflows/review/` in all static/ and prompts/ — update or remove references
<!-- /tasks -->

## Constraints

<!-- constraints -->
- One subagent per competency — platform files in `{name}-platforms/` subdirectory, not discoverable as separate competencies by `01-scope.md`
- testing.md is fully static — no prompt, no generation, no links to platform files
- Competency content injected via ShellStep — no LLM Read tool calls for competency files
- Manifest conditionals control which platform files are deployed per project
<!-- /constraints -->

## Implementation Notes

Final structure:

```
.workflows/code-review/
├── workflow.py
├── prompts/
│   ├── 01-scope.md
│   ├── 02-review.md
│   ├── 03-synthesize.md
│   └── 04-defer.md
└── competencies/
    ├── architecture.md
    ├── security.md
    ├── performance.md
    ├── data-integrity.md
    ├── simplicity.md
    ├── protocol-completeness.md
    ├── python.md                    # conditional: has_python
    ├── typescript.md                # conditional: has_typescript
    ├── testing.md                   # conditional: has_tests
    └── testing-platforms/
        ├── pytest.md                # conditional: has_python
        └── jest.md                  # conditional: has_typescript
```

Flow during code-review:
1. `01-scope.md` — LLM lists `competencies/*.md`, selects relevant ones by file patterns
2. `ParallelEachBlock` iterates over selected competency names
3. `ShellStep` cats `{name}.md` + `{name}-platforms/*.md` → content into `{{variables.competency_rules}}`
4. `02-review.md` receives competency rules inline — zero Read tool calls

## Verification

<!-- verification -->
```bash
# Verify old location is gone
test ! -d memento/static/memory_bank/workflows/review && echo "Old review dir removed"
# Verify new location
ls memento/static/workflows/code-review/competencies/
# Verify prompts removed
test ! -f memento/prompts/memory_bank/workflows/review/testing.md.prompt && echo "Testing prompt removed"
test ! -f memento/prompts/memory_bank/guides/code-review-guidelines.md.prompt && echo "Code review guidelines prompt removed"
# Verify platform files
test -f memento/static/workflows/code-review/competencies/testing-platforms/pytest.md && echo "pytest exists"
test -f memento/static/workflows/code-review/competencies/testing-platforms/jest.md && echo "jest exists"
# Verify 02-review.md uses injected content, not file path
grep 'competency_rules' memento/static/workflows/code-review/prompts/02-review.md && echo "02-review uses injected content"
# Verify 01-scope.md uses new path
grep 'code-review/competencies' memento/static/workflows/code-review/prompts/01-scope.md && echo "01-scope path updated"
# Verify no old references
grep -r 'workflows/review/' memento/static/ memento/prompts/ | grep -v '.pyc' || echo "No old path references"
grep -r 'code-review-guidelines' memento/static/ memento/prompts/ | grep -v '.pyc' || echo "No code-review-guidelines references"
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento/static/memory_bank/workflows/review/ (all files)
- memento/static/workflows/code-review/workflow.py
- memento/static/workflows/code-review/prompts/01-scope.md
- memento/static/workflows/code-review/prompts/02-review.md
- memento/prompts/memory_bank/workflows/review/testing.md.prompt
- memento/prompts/memory_bank/guides/code-review-guidelines.md.prompt
- memento/static/manifest.yaml
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
