# Memento Plugin — Developer Guide

**This is a META-PROJECT**: It generates Memory Bank documentation systems for OTHER projects, not for itself.

## Architecture

### Three Content Types

| Type             | Source                                           | How Deployed              | When to Use                             |
| ---------------- | ------------------------------------------------ | ------------------------- | --------------------------------------- |
| **Prompt-based** | `prompts/*.prompt`                               | LLM generates per-project | Content that must adapt to tech stack   |
| **Static**       | `static/` + `manifest.yaml`                      | Copied as-is              | Universal workflows, checklists, agents |
| **Plugin-only**  | `commands/`, `agents/`, `.claude-plugin/skills/` | Never deployed            | Generation/maintenance tools            |

### Two-Phase Generation

**Phase 1 (Planning)**: detect-tech-stack skill scans project → `project-analysis.json` → evaluate conditionals → `generation-plan.md`

**Phase 2 (Generation)**: Copy static files from manifest → spawn one agent per prompt file → write to target paths

### Directory Structure

```
memento/
├── prompts/                 # LLM generation instructions (18 prompt files)
│   ├── SCHEMA.md            # Prompt format spec — READ THIS FIRST
│   ├── anti-patterns.md     # Quality rules for generated content
│   ├── CLAUDE.md.prompt     # Root onboarding file
│   └── memory_bank/         # guides/, workflows/, patterns/
├── static/                  # Deployed as-is (40 manifest entries)
│   ├── manifest.yaml        # File list with conditionals
│   ├── memory_bank/workflows/  # workflows + review/ checklists
│   ├── agents/              # test-runner, developer, design-reviewer, research-analyst
│   ├── commands/            # all slash commands (10 files)
│   └── skills/              # commit, defer, load-context, update-memory-bank-protocol
├── commands/                # Plugin commands (require plugin installed)
├── agents/                  # environment-generator (plugin's own agent)
├── .claude-plugin/skills/   # detect-tech-stack, fix-broken-links, check-redundancy, analyze-local-changes
└── scripts/                 # validate-links.py, check-redundancy.py
```

## Development Workflow

### Adding a Prompt Template

1. Create `.prompt` file in `prompts/memory_bank/[guides|workflows|patterns]/`
2. Add YAML frontmatter (see `prompts/SCHEMA.md` for format)
3. Write generation instructions — NOT final content
4. Follow rules from `prompts/anti-patterns.md`
5. Test with `/create-environment` on a sample project

### Adding a Static File

1. Create file in `static/` (appropriate subdirectory)
2. Add entry to `static/manifest.yaml` with conditional
3. Run `python skills/analyze-local-changes/scripts/analyze.py recompute-source-hashes --plugin-root .` to update `source-hashes.json`
4. Test generation to verify copying

### Key Rules

-   Prompt code examples must show **framework patterns** with generic names (Item, Button), never project-specific models
-   Commands in prompts must use `{commands.*}` variables from project-analysis.json, never hardcoded
-   See `prompts/SCHEMA.md` for available variables and full schema

## Quality Standards

-   **No placeholders** in generated output
-   **<10% redundancy** (run `python scripts/check-redundancy.py <file>`)
-   **Valid links** (run `python scripts/validate-links.py`)
-   **Pattern-based examples**, not hallucinated project-specific code
-   Full rules: `prompts/anti-patterns.md`

## Testing

1. Create sample project with known stack (e.g., Django + React)
2. Run `/create-environment`
3. Verify: no placeholders, correct conditionals, valid links
4. Check generated content uses correct commands (e.g., `uv run pytest` not `pytest`)

## Common Tasks

**Update prompt template**: Edit in `prompts/` → run `recompute-source-hashes` → test on sample project → run validation scripts

**Update static file**: Edit in `static/` → run `recompute-source-hashes` → test generation

**Add new conditional**: Add detection in `skills/detect-tech-stack/scripts/detect.py` → update `prompts/SCHEMA.md` → use in frontmatter `conditional:` field

**Fix generated content quality**: Identify issue → update prompt instructions → add to `prompts/anti-patterns.md` if general → regenerate and validate

## Quick Reference

**Prompt priorities**: 1-40 Memory Bank docs, 50-59 agents, 60-69 commands

**Common conditionals**: `null` (always), `has_backend`, `has_frontend`, `has_database`, `has_tests`, `backend_framework == 'Django'`

**Key files**: `prompts/SCHEMA.md` (format spec), `prompts/anti-patterns.md` (quality rules), `static/manifest.yaml` (static file registry), `agents/environment-generator.md` (generation agent)

---

For user-facing documentation see `README.md`. For architecture details see `docs/SPECIFICATION.md`.
