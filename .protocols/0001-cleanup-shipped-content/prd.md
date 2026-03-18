# Cleanup Shipped Content — Requirements

## Problem Statement

The Memory Bank content shipped to target projects (prompts + static files) has accumulated redundancy and structural issues:

1. Three core files (product_brief, tech_stack, architecture) duplicate each other significantly (~40% overlap)
2. Agent documentation is disproportionately large relative to actual usage — custom agents are rarely used, but documentation treats them as central
3. Testing review competency is generated via prompt despite being mostly universal content — doesn't need generation
4. Commands in `.claude/commands/` are thin wrappers around prompt-based workflows — should be skills with co-located workflow files

## Requirements

### 1. Deduplicate product_brief / tech_stack / architecture

- **product_brief**: only "what this project does" + links. No technology listing, no architecture description.
- **tech_stack**: dependencies, tools, versions, commands. No infrastructure/security/performance speculation. Cross-references to backend/frontend guides for directory structure details.
- **architecture**: conceptual system design — components, data flow, decisions, diagrams. No tech stack listing (link to tech_stack). Remove speculative sections (Performance, Scalability, Security Architecture, Deployment Architecture).
- Duplicated information replaced with cross-references.

### 2. Remove unused agents, simplify agent documentation

- Remove `agent-orchestration.md` static file (duplicates handbook content, outdated)
- Convert `design-reviewer` and `research-analyst` agents to skills (with fork model)
- Remove or heavily simplify `ai-agent-handbook.md` prompt — it describes skills as "agents" and documents non-existent agents (@Developer)
- Update all cross-references in other docs

### 3. Restructure testing & review competencies

- Move ALL review competencies from `.memory_bank/workflows/review/` to `.workflows/code-review/competencies/`
- Make testing competency fully static (delete prompt), with platform-specific files in `testing-platforms/` subdirectory
- Inject competency content into review prompts via ShellStep (no LLM Read tool calls)
- Remove `code-review-guidelines.md` prompt (not used by any process)
- Add coverage step to develop workflow (initial check + retry loop)
- Remove testing guide prompts (testing.md, testing-backend.md, testing-frontend.md) — actionable rules embedded in develop workflow prompts

### 4. Migrate commands to skills, eliminate `.memory_bank/workflows/`

- Convert 5 commands to skills: create-prd, create-spec, create-protocol, update-memory-bank, doc-gardening
- Move corresponding workflow files into skill folders
- Merge `update-memory-bank` + `update-memory-bank-protocol` into one skill
- Keep `prime.md` as command (too simple for skill)
- Inline `bug-fixing.md` content into develop workflow explore prompt, delete file
- Inline `commit-message-rules.md` into commit workflow analyze prompt, delete file
- Delete `git-worktree-workflow.md` (logic in workflow engine code)
- Eliminate `.memory_bank/workflows/` directory entirely

## Non-Goals

- Changing the generation pipeline itself (detect-tech-stack, create-environment)
- Rewriting review competency static files (architecture, security, performance, etc.) — content stays, only location changes
- Changing the prompt schema format

## Acceptance Criteria

- No content duplication between product_brief, tech_stack, and architecture
- No references to @Developer agent anywhere in shipped content
- `agent-orchestration.md` removed
- Testing review competency is static, with platform files in `testing-platforms/`
- Competency content injected via ShellStep (no Read tool calls in code-review)
- Coverage step in develop workflow (RetryBlock)
- Commands directory contains only `prime.md`
- `.memory_bank/workflows/` directory does not exist
- Review competencies in `.workflows/code-review/competencies/`
- README output ~25–35 lines (down from 120–220)
- `code-review-guidelines.md` prompt deleted
- All testing guide prompts deleted
- `uv run pytest` passes
- Source hashes recomputed

## Source

Original source: conversation analysis of shipped prompts and static files
Captured: 2026-03-18
