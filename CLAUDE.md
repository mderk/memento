# Memento Plugin — Developer Guide

**This is a META-PROJECT**: it generates Memory Bank documentation systems for OTHER projects, not for itself.

If you arrived via `AGENTS.md`: that file is intentionally a thin wrapper so agents reliably load this `CLAUDE.md`. **Do not duplicate rules in `AGENTS.md`.**

## What matters in this repo (system of record)

This repository is primarily **prompt engineering + documentation harness**:

-   **`prompts/`**: generation instructions (the product surface)
-   **`static/` + `static/manifest.yaml`**: shipped-as-is workflows/commands/agents/skills
-   **Plugin-only implementation**: `commands/`, `agents/`, `skills/`, `scripts/`

Rule of thumb: if it gets deployed into user projects, it must be in `prompts/` or `static/`.

## Harness quick start (after any meaningful change)

### Golden commands

After changes to `prompts/**` or `static/**`, always run:

```bash
python skills/analyze-local-changes/scripts/analyze.py recompute-source-hashes --plugin-root .
uv run pytest
```

### Change type → required steps

| You changed                                                            | Also update                                                                                  | Then run        |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | --------------- |
| `prompts/**/*.prompt`                                                  | `source-hashes.json` (recompute)                                                             | `uv run pytest` |
| `static/**` content                                                    | `static/manifest.yaml` (if adding/removing shipped files) + `source-hashes.json` (recompute) | `uv run pytest` |
| `static/manifest.yaml`                                                 | Ensure new files exist + `source-hashes.json` (recompute)                                    | `uv run pytest` |
| Python tooling (`skills/**`, `scripts/**`)                             | Add/adjust tests if behavior changes                                                         | `uv run pytest` |

## Mechanical invariants (must stay true)

-   **Single entry point**: `CLAUDE.md` is the only rulebook. `AGENTS.md` is a wrapper.
-   **Wrappers must not drift**: `AGENTS.md` and `static/AGENTS.md` must contain exactly `READ ./CLAUDE.md`.
-   **Hashes must be accurate**: after any prompt/static change, `source-hashes.json` must be recomputed.
-   **Template legibility is enforced** (via tests):
    -   internal links between shipped static workflows must resolve
    -   Memory Bank README prompt must stay “map-sized” (not a manual)
    -   README prompt must list only shipped commands

## Architecture

### Three Content Types

| Type             | Source                                           | How Deployed              | When to Use                             |
| ---------------- | ------------------------------------------------ | ------------------------- | --------------------------------------- |
| **Prompt-based** | `prompts/*.prompt`                               | LLM generates per-project | Content that must adapt to tech stack   |
| **Static**       | `static/` + `manifest.yaml`                      | Copied as-is              | Universal workflows, checklists, agents |
| **Plugin-only**  | `commands/`, `agents/`, `skills/`, `scripts/`    | Never deployed            | Generation/maintenance tools            |

### Two-Phase Generation

**Phase 1 (Planning)**: detect-tech-stack skill scans project → `project-analysis.json` → evaluate conditionals → `generation-plan.md`

**Phase 2 (Generation)**: Copy static files from manifest → spawn one agent per prompt file → write to target paths

### Directory Structure

```
memento/
├── prompts/                 # LLM generation instructions (.prompt templates)
│   ├── SCHEMA.md            # Prompt format spec — READ THIS FIRST
│   ├── anti-patterns.md     # Quality rules for generated content
│   ├── CLAUDE.md.prompt     # Root onboarding file
│   └── memory_bank/         # guides/, workflows/, patterns/
├── static/                  # Deployed as-is (see static/manifest.yaml)
│   ├── manifest.yaml        # File list with conditionals
│   ├── memory_bank/workflows/  # workflows + review/ checklists
│   ├── agents/              # test-runner, developer, design-reviewer, research-analyst
│   ├── commands/            # slash commands (deployed to projects)
│   └── skills/              # commit, defer, load-context
├── commands/                # Plugin commands (require plugin installed)
├── agents/                  # environment-generator (plugin's own agent)
└── skills/                  # Plugin skills (detect-tech-stack, fix-broken-links, check-redundancy, analyze-local-changes)
```

## Development Workflow

### Adding a Prompt Template

1. Create `.prompt` file in `prompts/memory_bank/[guides|workflows|patterns]/`
2. Add YAML frontmatter (see `prompts/SCHEMA.md` for format)
3. Write generation instructions — NOT final content
4. Follow rules from `prompts/anti-patterns.md`
5. Test with `/memento:create-environment` on a sample project

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
-   **<10% redundancy** (see `prompts/anti-patterns.md`)
-   **Valid links** (enforced by template tests; also validate in sample projects)
-   **Pattern-based examples**, not hallucinated project-specific code
-   Full rules: `prompts/anti-patterns.md`

## Testing

1. Create sample project with known stack (e.g., Django + React)
2. Run `/memento:create-environment`
3. Verify: no placeholders, correct conditionals, valid links
4. Check generated content uses correct commands (e.g., `uv run pytest` not `pytest`)

## Common Tasks

**Update prompt template**: Edit in `prompts/` → recompute `source-hashes.json` → `uv run pytest` → test on a sample project

**Update static file**: Edit in `static/` (+ `static/manifest.yaml` if needed) → recompute `source-hashes.json` → `uv run pytest`

**Add new conditional**: Add detection in `skills/detect-tech-stack/scripts/detect.py` → update `prompts/SCHEMA.md` → use in frontmatter `conditional:` field

**Fix generated content quality**: Identify issue → update prompt instructions → add to `prompts/anti-patterns.md` if general → regenerate and validate

## Quick Reference

**Prompt priorities**: 1-40 Memory Bank docs, 50-59 agents, 60-69 commands

**Common conditionals**: `null` (always), `has_backend`, `has_frontend`, `has_database`, `has_tests`, `backend_framework == 'Django'`

**Key files**: `prompts/SCHEMA.md` (format spec), `prompts/anti-patterns.md` (quality rules), `static/manifest.yaml` (static file registry), `agents/environment-generator.md` (generation agent)

---

For user-facing documentation see `README.md`. For architecture details see `docs/SPECIFICATION.md`.
