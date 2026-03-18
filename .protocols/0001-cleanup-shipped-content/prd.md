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

### 3. Convert testing review competency to static

- Extract universal rules into a static `review/testing.md` (conditional: `has_tests`)
- Create conditional framework-specific static files (e.g., `review/testing-pytest.md` conditional: `has_python`) — following the pattern of `python.md`/`typescript.md`
- Remove `testing.md.prompt` from prompts/

### 4. Migrate commands to skills

- Convert 5 commands to skills: create-prd, create-spec, create-protocol, update-memory-bank, doc-gardening
- Move corresponding workflow files from `.memory_bank/workflows/` into skill folders
- Merge `update-memory-bank` + `update-memory-bank-protocol` into one skill with optional protocol-path argument
- Keep `prime.md` as command (too simple for skill)
- `.memory_bank/workflows/` retains only reference docs (bug-fixing, commit-message-rules, git-worktree-workflow) and review competencies

## Non-Goals

- Changing workflow engine workflows (develop, code-review, testing, commit, etc.) — those stay in `.workflows/`
- Changing the generation pipeline itself (detect-tech-stack, create-environment)
- Rewriting review competency static files (architecture, security, performance, etc.)
- Changing the prompt schema format

## Acceptance Criteria

- No content duplication between product_brief, tech_stack, and architecture (each section exists in exactly one file)
- No references to @Developer agent anywhere in shipped content
- `agent-orchestration.md` removed from manifest and static/
- Testing review competency files are static with conditionals, no prompt template
- Commands directory contains only `prime.md`
- All migrated workflows accessible as skills
- `uv run pytest` passes
- Source hashes recomputed

## Source

Original source: conversation analysis of shipped prompts and static files
Captured: 2026-03-18
