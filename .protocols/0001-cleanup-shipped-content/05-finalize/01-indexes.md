---
id: 05-finalize-01-indexes
status: pending
estimate: 2h
---

# Update Indexes, Prompts, Manifest, and Hashes

## Objective

<!-- objective -->
Update all navigation files, remaining prompts, and infrastructure to reflect changes from previous steps. Fix stale references, recompute hashes, run tests.
<!-- /objective -->

## Tasks

<!-- tasks -->
### Rewrite README.md prompt — strip to essentials

- [ ] Rewrite `memento/prompts/memory_bank/README.md.prompt` for a ~25–35 line output (down from 120–220). The README is loaded on every `/prime` — every line must earn its place in the context window. Target structure:
  ```markdown
  # Memory Bank: {Project Name}

  **Last Updated**: {date}
  **Type**: {project_type}
  **Stack**: {stack summary}

  ## Quick Start

  Run `/prime` to load context. Must-read before coding:
  - `./product_brief.md` — what this project is
  - `./tech_stack.md` — dependencies and commands
  - `./guides/architecture.md` — system design

  ## Guides

  | Guide | Purpose |
  |-------|---------|
  | [getting-started.md](./guides/getting-started.md) | Setup and first contribution |
  | [architecture.md](./guides/architecture.md) | System design, data flow |
  | [backend.md](./guides/backend.md) | Backend patterns and conventions |
  | [frontend.md](./guides/frontend.md) | Frontend patterns and components |
  | [visual-design.md](./guides/visual-design.md) | Design system, accessibility |

  ## Patterns

  See [patterns/index.md](./patterns/index.md).
  ```
- [ ] Remove these sections from the prompt entirely:
  - "What is the Memory Bank?" — agent already knows
  - Quick Start "For Developers" — human-facing, not for AI
  - Test command code block — `/run-tests` skill handles this, command in tech_stack
  - Workflows section — `.memory_bank/workflows/` no longer exists; skills are self-discoverable by Claude Code
  - Directory Structure — trivial after cleanup, agent can `ls`
  - Navigation Tips — agent knows grep/glob
  - Maintenance — meta-information, not needed during development
  - Available Commands table — Claude Code knows its own skills from SKILL.md frontmatter
  - Available Agents table — same
- [ ] Conditional logic stays: backend.md (if has_backend), frontend.md + visual-design.md (if has_frontend)
- [ ] Update target_lines in frontmatter: 25–35 (from 120–220)
- [ ] Verify all links point to files that will exist after generation

### Update guides/index.md prompt

- [ ] Update `memento/prompts/memory_bank/guides/index.md.prompt`:
  - Remove from guide listings: ai-agent-handbook, code-review-guidelines, testing.md, testing-backend.md, testing-frontend.md
  - Keep: getting-started, architecture, backend, frontend, visual-design
  - Remove "Quality & Testing" category (no testing guides remain)
  - Remove "Process & Workflow" category (ai-agent-handbook removed)
  - Update conditional logic documentation
  - Remove references to `../workflows/index.md` (directory gone)

### Update develop workflow classify prompt

- [ ] Update `memento/static/workflows/develop/prompts/00-classify.md`:
  - Remove from table: `| Bug fix | .memory_bank/workflows/bug-fixing.md |` (deleted, content in explore prompt)
  - Remove from table: `| Testing | .memory_bank/guides/testing.md |` (deleted)
  - Keep: backend.md, frontend.md, api-design.md references

### Update remaining guide prompts

- [ ] Update `memento/prompts/memory_bank/guides/getting-started.md.prompt`:
  - Remove references to code-review-guidelines.md, testing.md, bug-fixing.md
  - Update any `../workflows/` links (directory gone)
- [ ] Update `memento/prompts/memory_bank/guides/backend.md.prompt`:
  - Remove references to testing-backend.md in References section
  - Update any stale links
- [ ] Update `memento/prompts/memory_bank/guides/frontend.md.prompt`:
  - Remove references to testing-frontend.md in References section
  - Remove reference to testing.md if present
  - Update any stale links
- [ ] Update `memento/prompts/memory_bank/guides/visual-design.md.prompt`:
  - Remove reference to testing.md if present
  - Update any stale links

### Update patterns

- [ ] Check `memento/prompts/memory_bank/patterns/api-design.md.prompt` for stale references
- [ ] Check `memento/prompts/memory_bank/patterns/index.md.prompt` for stale references

### Consolidate manifest

- [ ] Verify `memento/static/manifest.yaml`:
  - All entries point to files that exist
  - No stale entries from previous steps remain
  - No duplicate entries
  - Entries logically grouped with comments
  - All new files from steps 02–04 properly added

### Stale reference sweep

- [ ] Run grep sweep for all removed files:
  ```bash
  grep -r 'ai-agent-handbook' memento/static/ memento/prompts/
  grep -r 'code-review-guidelines' memento/static/ memento/prompts/
  grep -r 'agent-orchestration' memento/static/ memento/prompts/
  grep -r 'testing-backend\.md\|testing-frontend\.md' memento/static/ memento/prompts/
  grep -r 'guides/testing\.md' memento/static/ memento/prompts/
  grep -r 'workflows/bug-fixing' memento/static/ memento/prompts/
  grep -r 'workflows/commit-message' memento/static/ memento/prompts/
  grep -r 'workflows/git-worktree' memento/static/ memento/prompts/
  grep -r 'workflows/index\.md' memento/static/ memento/prompts/
  grep -r 'commands/create-prd\|commands/create-spec\|commands/create-protocol' memento/static/ memento/prompts/
  grep -r 'commands/update-memory-bank\|commands/doc-gardening' memento/static/ memento/prompts/
  ```
- [ ] Fix any remaining references found

### Recompute hashes and run tests

- [ ] Recompute source hashes:
  ```bash
  python memento/skills/analyze-local-changes/scripts/analyze.py recompute-source-hashes --plugin-root memento
  ```
- [ ] Run tests:
  ```bash
  uv run pytest
  ```
- [ ] Fix any test failures (expected: template validation tests, link validation tests)
<!-- /tasks -->

## Constraints

<!-- constraints -->
- README.md prompt must stay within "map-sized" target (enforced by tests)
- All internal links in static files must resolve (enforced by tests)
- README prompt must list only shipped commands/skills (enforced by tests)
- Source hashes must be accurate after all prompt/static changes
<!-- /constraints -->

## Implementation Notes

Summary of what was removed/moved across all steps:

**Deleted prompts:**
- ai-agent-handbook.md.prompt
- code-review-guidelines.md.prompt
- testing.md.prompt (guide)
- testing-backend.md.prompt
- testing-frontend.md.prompt
- testing.md.prompt (review competency)

**Deleted static files:**
- agents/design-reviewer.md, agents/research-analyst.md → converted to skills
- memory_bank/workflows/ → entire directory eliminated
- commands/create-prd.md, create-spec.md, create-protocol.md, update-memory-bank.md, update-memory-bank-protocol.md, doc-gardening.md → converted to skills

**Moved:**
- memory_bank/workflows/review/*.md → .workflows/code-review/competencies/

**New files:**
- skills/design-reviewer/SKILL.md, skills/research-analyst/SKILL.md
- skills/create-prd/, create-spec/, create-protocol/, update-memory-bank/, doc-gardening/ (SKILL.md + workflow.md each)
- workflows/code-review/competencies/testing.md (static)
- workflows/code-review/competencies/testing-platforms/pytest.md, jest.md
- workflows/develop/prompts/03d-coverage.md

## Verification

<!-- verification -->
```bash
# Recompute hashes
python memento/skills/analyze-local-changes/scripts/analyze.py recompute-source-hashes --plugin-root memento
# Run full test suite
uv run pytest
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento/prompts/memory_bank/README.md.prompt
- memento/prompts/memory_bank/guides/index.md.prompt
- memento/static/workflows/develop/prompts/00-classify.md
- memento/prompts/memory_bank/guides/getting-started.md.prompt
- memento/prompts/memory_bank/guides/backend.md.prompt
- memento/prompts/memory_bank/guides/frontend.md.prompt
- memento/static/manifest.yaml
- memento/source-hashes.json
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] Update `.memory_bank/README.md` — structure changed significantly
