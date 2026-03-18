---
id: 04-commands-01-migrate
status: pending
estimate: 2h
---

# Migrate Commands to Skills

## Objective

<!-- objective -->
Convert 5 command files into self-contained skills with co-located workflow files. Inline bug-fixing, commit-message-rules, and git-worktree-workflow content into workflow prompts. Eliminate `.memory_bank/workflows/` entirely. After this step, `.claude/commands/` contains only `prime.md`.
<!-- /objective -->

## Tasks

<!-- tasks -->
- [ ] Create `memento/static/skills/create-prd/SKILL.md` — description + context loading instructions
- [ ] Move `memento/static/memory_bank/workflows/create-prd.md` → `memento/static/skills/create-prd/workflow.md`
- [ ] Create `memento/static/skills/create-spec/SKILL.md`
- [ ] Move `memento/static/memory_bank/workflows/create-spec.md` → `memento/static/skills/create-spec/workflow.md`
- [ ] Create `memento/static/skills/create-protocol/SKILL.md`
- [ ] Move `memento/static/memory_bank/workflows/create-protocol.md` → `memento/static/skills/create-protocol/workflow.md`
- [ ] Create `memento/static/skills/update-memory-bank/SKILL.md` — accepts optional `<protocol-path>` argument
- [ ] Move `memento/static/memory_bank/workflows/update-memory-bank.md` → `memento/static/skills/update-memory-bank/workflow.md`
- [ ] Create `memento/static/skills/doc-gardening/SKILL.md`
- [ ] Move `memento/static/memory_bank/workflows/doc-gardening.md` → `memento/static/skills/doc-gardening/workflow.md`
- [ ] Delete old command files:
  - `memento/static/commands/create-prd.md`
  - `memento/static/commands/create-spec.md`
  - `memento/static/commands/create-protocol.md`
  - `memento/static/commands/update-memory-bank.md`
  - `memento/static/commands/update-memory-bank-protocol.md`
  - `memento/static/commands/doc-gardening.md`
- [ ] Update `memento/static/manifest.yaml`:
  - Remove old command entries and old workflow-doc entries
  - Add new skill entries (SKILL.md + workflow.md for each)
- [ ] Update internal links in workflow.md files (relative paths changed since file moved)

### Remove bug-fixing.md

- [ ] Add to `01-explore.md` prompt (develop workflow) a brief bug-specific hint:
  ```markdown
  ### If bug fix
  - Reproduce the bug first — find the exact input/state that triggers it
  - Check similar code paths for the same pattern (bugs often repeat)
  ```
- [ ] Delete `memento/static/memory_bank/workflows/bug-fixing.md`
- [ ] Remove bug-fixing.md entry from `memento/static/manifest.yaml`

### Inline commit-message-rules.md into commit workflow

- [ ] Embed the rules (45 lines) directly into `memento/static/workflows/commit/prompts/analyze.md` — replace the instruction "Read the commit message rules at ..." with the actual rules inline
- [ ] Delete `memento/static/memory_bank/workflows/commit-message-rules.md`
- [ ] Remove commit-message-rules.md entry from `memento/static/manifest.yaml`

### Remove git-worktree-workflow.md

- [ ] Delete `memento/static/memory_bank/workflows/git-worktree-workflow.md`
- [ ] Remove git-worktree-workflow.md entry from `memento/static/manifest.yaml`
- [ ] (No content to embed — worktree logic is fully implemented in process-protocol/workflow.py and helpers.py)

### Remove .memory_bank/workflows/ entirely

- [ ] Delete `memento/static/memory_bank/workflows/index.md`
- [ ] Remove index.md entry from `memento/static/manifest.yaml`
- [ ] Remove the `memento/static/memory_bank/workflows/` directory (should be empty after all removals)
<!-- /tasks -->

## Constraints

<!-- constraints -->
- `prime.md` stays as a command — it's too simple for a skill (just "read these files")
- Skill SKILL.md format must match existing skills (commit, defer, develop, etc.)
- `update-memory-bank` skill replaces both `update-memory-bank` and `update-memory-bank-protocol` commands
- Workflow .md files keep their content, only location changes
- Internal links within workflow files must be updated for new relative paths
<!-- /constraints -->

## Implementation Notes

### SKILL.md template for prompt-based workflows:

```yaml
---
name: create-prd
description: Generate a PRD for a feature using Memory Bank context
argument-hint: [feature description]
---
```

```markdown
# Create PRD

## Context Preparation

Read Memory Bank context:
- `.memory_bank/README.md`, `.memory_bank/product_brief.md`, `.memory_bank/tech_stack.md`

## Workflow

Follow the workflow defined in:
**`${CLAUDE_SKILL_DIR}/workflow.md`**
```

### Merged update-memory-bank skill:

```markdown
# Update Memory Bank

## Usage

- `/update-memory-bank` — standard update (changes since last update)
- `/update-memory-bank <protocol-path>` — post-protocol update (collect findings)

## Workflow

If `$ARGUMENTS` contains a protocol path → follow "After Protocol Completion" section.
Otherwise → follow standard process (Steps 1–6).

**`${CLAUDE_SKILL_DIR}/workflow.md`**
```

### .memory_bank/workflows/ is fully eliminated

No files remain — delete the directory entirely (including `index.md`, which was navigation for a now-empty folder; its content is covered by README's skills listing).

Everything removed or relocated:
- `review/*.md` → `.workflows/code-review/competencies/` (step 03-testing/01)
- `bug-fixing.md` → develop workflow `01-explore.md` prompt
- `commit-message-rules.md` → commit workflow `analyze.md` prompt
- `git-worktree-workflow.md` → deleted (logic in process-protocol code)
- `create-prd.md`, `create-spec.md`, `create-protocol.md`, `update-memory-bank.md`, `doc-gardening.md` → skill folders
- `index.md` → deleted (README covers navigation)

## Verification

<!-- verification -->
```bash
# Verify old commands are gone (only prime.md remains)
ls memento/static/commands/
# Verify new skill directories exist
for skill in create-prd create-spec create-protocol update-memory-bank doc-gardening; do
  test -f "memento/static/skills/$skill/SKILL.md" && test -f "memento/static/skills/$skill/workflow.md" && echo "$skill: OK"
done
# Verify workflow files removed from memory_bank/workflows/
# Verify entire workflows directory is gone
test ! -d memento/static/memory_bank/workflows && echo "workflows/ directory removed"
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento/static/commands/
- memento/static/memory_bank/workflows/
- memento/static/skills/commit/SKILL.md (reference for format)
- memento/static/manifest.yaml
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
