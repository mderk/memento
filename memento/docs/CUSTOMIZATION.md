# Customization Guide

## How Customization Works

Memory Bank files are **read and executed by AI agents**. Workflows, commands, and agents contain step-by-step procedures that AI agent follows literally. Guides and patterns serve as knowledge context that shapes agent decisions.

**Customize by prompting the agent**, not by hand-editing files. The agent understands file formats, cross-references, and conventions — describe what you want changed, and it will make consistent updates across affected files.

**Two customization levels:**

1. **Project-level** — modify generated files in your project (most common)
2. **Plugin-level** — fork memento and modify prompts/static files

## What to Customize First

After running `/memento:create-environment`, these files benefit most from project-specific content:

| Priority | File                                | What to add                                                    |
| -------- | ----------------------------------- | -------------------------------------------------------------- |
| 1        | `product_brief.md`                  | Product vision, target users, key features                     |
| 2        | `tech_stack.md`                     | Verify detected stack, add third-party services, infra details |
| 3        | `guides/getting-started.md`         | Setup instructions, dev environment, onboarding steps          |
| 4        | `guides/architecture.md`            | System diagram, component interactions, data flows             |
| 5        | `guides/backend.md`                 | Code organization, common patterns, conventions                |
| 6        | `guides/frontend.md`                | Component patterns, state management, styling approach         |
| 7        | `patterns/api-design.md`            | API conventions, error handling, pagination                    |
| 8        | `workflows/commit-message-rules.md` | Your team's commit conventions                                 |

All paths relative to `.memory_bank/`.

## Project-Level Customization

### Knowledge Files (guides, patterns, product_brief, tech_stack)

These files are **context** — they shape how agents understand your project. Freely add, restructure, or rewrite content.

**Effective prompts:**

```
"Update product_brief.md with our actual product: [describe your product, users, goals]"

"Add our Redis caching layer and Celery task queue to tech_stack.md and architecture.md"

"Document our authentication flow in architecture.md — we use Auth0 with JWT,
sessions in Redis, refresh token rotation"

"Add error handling patterns to backend.md — we use custom exception classes
that map to HTTP status codes"
```

### Agent Instruction Files (workflows, commands, agents)

These files are **executable** — agents follow them step by step. Preserve structure and mandatory phases. Customize by adding project-specific details within the existing flow.

**Safe customizations:**

-   Add project-specific commands and paths (your test runner, linter, deploy script)
-   Add review criteria to checklists in `workflows/review/`
-   Adjust parameters (coverage thresholds, timeout values)

**Do not:**

-   Remove mandatory phases or sub-agent invocations
-   Replace agent instructions with human process descriptions

**Effective prompts:**

```
"Add an accessibility competency to /code-review — check for ARIA attributes,
color contrast, keyboard navigation. Model it after the existing review
competencies in workflows/review/"

"Update testing-workflow.md to run our E2E suite:
`cd e2e && npx playwright test --project=chromium`"

"Adjust commit-message-rules.md — we use Conventional Commits with scopes:
feat(api):, fix(ui):, docs(guides):"
```

### Adding New Files

```
"Create an agent for database migration review. It should check for: backwards
compatibility, data loss risks, missing indexes on foreign keys, and proper
rollback migrations. Put it in .claude/agents/"

"Create a /deploy command that runs tests, builds Docker image, pushes to ECR,
and updates the ECS service. Require confirmation for production.
Put it in .claude/commands/"

"Add a workflow for our release process: tag version, generate changelog,
create GitHub release, deploy to staging, run smoke tests, promote to production.
Make it an agent-executable workflow in .memory_bank/workflows/"
```

## Plugin-Level Customization (Fork)

For organizations that want to customize the generation itself — what files are produced and how.

### Modifying Prompts

Prompt files (`.prompt`) are **generation instructions**, not final content. They tell the LLM how to create project-specific files.

```
"Add a new prompt for infrastructure.md guide — it should generate documentation
covering CI/CD pipeline, monitoring, alerting, and deployment environments.
Conditional on has_ci. Follow the format in prompts/SCHEMA.md"

"Modify the testing.md prompt to emphasize property-based testing and mutation
testing for projects that use Python"

"Update CLAUDE.md.prompt to include a section about our organization's security
policies — all generated CLAUDE.md files should reference the security review checklist"
```

### Adding Static Files

Static files are copied as-is to all projects. Use for universal workflows, checklists, and templates that don't need tech-specific adaptation.

1. Add file to `static/` (appropriate subdirectory)
2. Register in `static/manifest.yaml` with conditional
3. Run `recompute-source-hashes` to update hash tracking

See `prompts/SCHEMA.md` for the prompt format and `static/manifest.yaml` for conditional syntax.

## Keeping Updated

### After code changes

These deployed commands keep Memory Bank in sync with your evolving codebase — no regeneration needed:

-   `/update-memory-bank` — update documentation after code changes (run after significant refactors, new features, architecture shifts)
-   `/update-memory-bank-protocol` — update Memory Bank from Findings accumulated during protocol execution
-   `/doc-gardening` — periodic maintenance: link integrity, redundancy, freshness, knowledge promotion

### After plugin updates or tech stack changes

```bash
/memento:update-environment auto    # Detect what needs updating
```

Compares source hashes, detects tech stack changes, recommends which files to regenerate. Local changes are preserved via 3-way merge.

## Version Control

Commit to git:

-   `.memory_bank/` (all documentation)
-   `.claude/` (agents, commands, skills)
-   `CLAUDE.md` (onboarding)

These are auto-committed by the generation system (needed for 3-way merge on updates):

-   `.memory_bank/project-analysis.json` (generation metadata)
-   `.memory_bank/generation-plan.md` (generation plan with source hashes)

## Troubleshooting

### Broken Links

Run `/memento:fix-broken-links` to find and fix broken cross-references.

### Outdated Content

After a plugin update, run `/memento:update-environment auto` — it compares source hashes and recommends which files to regenerate, preserving local changes via 3-way merge.

### Redundancy

Use `/memento:check-redundancy <file>` to check for excessive duplication between files.

## Getting Help

-   **Issues**: [GitHub Issues](https://github.com/mderk/memento/issues)
-   **Documentation**: [README.md](../README.md)
