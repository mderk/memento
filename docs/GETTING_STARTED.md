# Getting Started with Claude AI Environment

This guide will help you set up an AI development environment in your project in less than 5 minutes.

## Prerequisites

-   **Claude Code CLI** installed
-   **Git** (optional but recommended)
-   **Project directory** with some code (or empty for new project)

**Note**: No Python or external dependencies required! Generation is powered by the LLM.

## Installation

### Step 1: Add Marketplace and Install

```bash
/plugin marketplace add mderk/memento
/plugin install memento-marketplace@memento
```

Restart Claude Code after installation.

### Step 2: Navigate to Your Project

```bash
cd /path/to/your-project
```

## Quick Start

### For New Projects

If you're starting a new project:

```bash
# Create project directory
mkdir my-awesome-app
cd my-awesome-app

# Initialize environment
/create-environment
```

The plugin will ask you questions about your project since it can't detect anything yet.

### For Existing Projects

If you have an existing project:

```bash
cd existing-project
/create-environment
```

The plugin will automatically detect your tech stack and ask for confirmation.

## Step-by-Step Walkthrough

### Example: Django + React Project

```bash
$ cd my-project
$ /create-environment

🚀 Phase 1: Creating generation plan...

🔍 Analyzing project structure...
  ✓ Found package.json (frontend)
  ✓ Found requirements.txt (backend)
  ✓ Found pytest.ini (testing)

📊 Detected stack:
  Backend: Django 5.0 (Python)
  Frontend: React 18.2 (TypeScript)
  Database: PostgreSQL (psycopg2)
  Testing: pytest + jest
  Structure: Monorepo (server/ + client/)

📝 Scanning generation prompts + static manifest...
  ✓ Scanned 18 prompt files (frontmatter only)
  ✓ Scanned 40 static file entries (manifest.yaml)
  ✓ Evaluated conditionals for your stack
  ✓ Created generation plan: .memory_bank/generation-plan.md

Ready to generate ~60 files. Reply with "Go" to proceed.

$ Go

🚀 Phase 2: Generating files...

📋 Copying static files...
  ✓ Copied .memory_bank/workflows/development-workflow.md (static)
  ✓ Copied .claude/commands/code-review.md (static)
  ... [13 workflows + 6 review checklists + 10 commands + 4 agents + 4 skills]

📦 Generating project-specific documentation...
  ✓ Generated CLAUDE.md (1/18)
  ✓ Generated .memory_bank/README.md (2/18)
  ✓ Generated .memory_bank/product_brief.md (3/18)
  ... [progress continues]
  ✓ Generated .memory_bank/patterns/api-design.md (18/18)

✅ Generation complete!

Generated structure:
  .memory_bank/  (docs + workflows + review checklists)
  .claude/agents/  (4 agents)
  .claude/commands/  (10 commands)
  .claude/skills/  (4 skills)
  CLAUDE.md  (onboarding guide)

Next steps:
  1. Review .memory_bank/README.md for navigation
  2. Customize .memory_bank/product_brief.md
  3. Try: /prime (load project context)
  4. Try: /code-review server/app.py (review code)
```

## Generated Structure

After running the command, you'll have:

```
your-project/
├── CLAUDE.md                      # AI assistant onboarding
├── .claude/
│   ├── agents/
│   │   ├── test-runner.md         # (static) Test execution
│   │   ├── developer.md           # (static) Code implementation
│   │   ├── design-reviewer.md     # (static, if frontend)
│   │   └── research-analyst.md    # (static)
│   ├── commands/
│   │   ├── code-review.md         # (static) Parallel competency review
│   │   ├── develop.md             # (static) Developer sub-agent
│   │   ├── merge-protocol.md      # (static) Protocol branch merge
│   │   ├── update-memory-bank.md  # (static) Post-change doc update
│   │   ├── prime.md               # (static) Load context
│   │   ├── run-tests.md           # (static) Test runner
│   │   ├── create-prd.md          # (static) PRD creation
│   │   ├── create-spec.md         # (static) Spec creation
│   │   ├── create-protocol.md     # (static) Protocol creation
│   │   └── process-protocol.md    # (static) Protocol execution
│   └── skills/
│       ├── commit/SKILL.md        # (static) Git commit with rules
│       ├── defer/                  # (static) Backlog management
│       ├── load-context/           # (static) Protocol context loader
│       └── update-memory-bank-protocol/  # (static) Post-protocol update
└── .memory_bank/
    ├── README.md                  # Navigation hub
    ├── product_brief.md           # Product vision
    ├── tech_stack.md              # Tech details
    ├── guides/
    │   ├── index.md
    │   ├── ai-agent-handbook.md
    │   ├── architecture.md
    │   ├── backend.md             # (if backend)
    │   ├── frontend.md            # (if frontend)
    │   ├── visual-design.md       # (if frontend)
    │   ├── testing.md             # Hub: philosophy, pyramid
    │   ├── testing-backend.md     # (if backend) Backend patterns
    │   ├── testing-frontend.md    # (if frontend) Frontend patterns
    │   ├── getting-started.md
    │   └── code-review-guidelines.md
    ├── workflows/
    │   ├── index.md                # (static)
    │   ├── development-workflow.md # (static)
    │   ├── bug-fixing.md           # (static)
    │   ├── code-review-workflow.md # (static)
    │   ├── testing-workflow.md     # (static)
    │   ├── create-prd.md           # (static)
    │   ├── create-spec.md          # (static)
    │   ├── create-protocol.md      # (static)
    │   ├── process-protocol.md     # (static)
    │   ├── agent-orchestration.md  # (static)
    │   ├── git-worktree-workflow.md # (static)
    │   ├── commit-message-rules.md # (static)
    │   ├── update-memory-bank.md   # (static)
    │   └── review/                 # Code review competency checklists
    └── patterns/
        ├── index.md
        └── api-design.md
```

## Using Your AI Environment

### 1. Load Context

Before starting work, load the Memory Bank context:

```bash
/prime
```

This reads key documentation files and prepares the AI assistant with project knowledge.

### 2. Code Review

After making changes:

```bash
/code-review path/to/file.py path/to/another.ts
```

The `/code-review` command will:

-   Spawn parallel sub-agents per review competency (architecture, security, performance, etc.)
-   Check code quality and identify issues
-   Synthesize results into a unified report with APPROVE/REQUEST CHANGES recommendation

### 3. Run Tests

Before committing:

```bash
/run-tests
```

The `@test-runner` agent will:

-   Auto-detect test framework
-   Run tests
-   Report results with clear formatting
-   Suggest fixes for failures

### 4. Start New Feature

When beginning a new feature:

```bash
# Step 1: Create PRD
/create-prd "user authentication system"

# Step 2: Create technical spec
/create-spec prd-user-auth.md

```

## Common Workflows

### Daily Development

```bash
# Morning: Load context
/prime

# During development: Review changes
/code-review src/new-feature.py

# Before commit: Run tests
/run-tests

# Before PR: Final review
/code-review $(git diff --name-only main)
```

### Feature Development

```bash
# Planning phase
/create-prd "feature description"
/create-spec prd-feature.md

# QA phase
/code-review --all-changed
/run-tests --coverage
```

### Bug Fixing

```bash
# Load context
/prime

# Review the bug area
/code-review src/buggy-module.py

# After fix: Test
/run-tests tests/test_buggy_module.py

# Final review
/code-review src/buggy-module.py
```

## Customization

### Update Product Brief

Edit `.memory_bank/product_brief.md` with your product vision:

```markdown
# Product Brief: My Awesome App

## Vision

[Describe what you're building and why]

## Target Users

[Who will use this?]

## Key Features

[What are the core features?]
```

### Update Tech Stack

If you add new dependencies, update `.memory_bank/tech_stack.md`:

```markdown
## Backend

-   **Framework**: Django 5.0
-   **Database**: PostgreSQL 15
-   **Cache**: Redis 7.2 ← NEW
-   **Task Queue**: Celery 5.3 ← NEW
```

### Add Custom Patterns

Create new pattern files in `.memory_bank/patterns/`:

```markdown
# Authentication Patterns

## JWT Token Flow

[Document your authentication pattern]
```

## Keeping Your Environment Updated

After initial setup, use `/update-environment` to keep documentation synchronized with your evolving codebase.

### Smart Detection Mode

```bash
/update-environment auto
```

Detects framework upgrades, new dependencies, database changes, and new plugin features. Recommends which files to update.

### Manual Updates

```bash
/update-environment workflows     # Update all workflow files
/update-environment guides        # Update all guides
/update-environment backend.md    # Update specific file
/update-environment all           # Full regeneration
```

### When to Update

-   After `npm install` / `pip install` (new dependencies)
-   After framework upgrades (React, Django, etc.)
-   After adding test frameworks (Playwright, Vitest)
-   After plugin updates (`/plugin update memento-marketplace@memento`)
-   Monthly maintenance (run `auto` to check for drift)

## Troubleshooting

### Detection Issues

**Problem**: Plugin didn't detect my framework

**Solution**:

-   Ensure config files are in project root (package.json, requirements.txt, etc.)
-   Check dependencies are listed correctly
-   Use manual selection if auto-detection fails

### File Conflicts

**Problem**: `.memory_bank/` already exists

**Solution**:

```bash
# Option 1: Backup and regenerate
mv .memory_bank .memory_bank.backup
/create-environment

# Option 2: Smart update (preserves local changes)
/update-environment auto
```

### Generation Errors

**Problem**: Generation failed with error

**Solution**:

-   Ensure write permissions in project directory
-   Check Claude Code logs for specific error
-   Try command again (LLM generation can sometimes fail)
-   Report issue with error message if persists

## Next Steps

1. **Explore Memory Bank**: Read `.memory_bank/README.md`
2. **Try Commands**: Experiment with `/prime`, `/code-review`, etc.
3. **Customize Guides**: Update project-specific documentation
4. **Share with Team**: Commit `.memory_bank/` and `.claude/` to version control

## Examples by Project Type

### Django API

```bash
cd django-api
/create-environment
# Detects: Django, PostgreSQL, pytest, DRF
# Generates: Backend-focused guides, API patterns
```

### React SPA

```bash
cd react-app
/create-environment
# Detects: React, TypeScript, Jest, Vite
# Generates: Frontend-focused guides, component patterns
```

### Full-Stack Monorepo

```bash
cd fullstack-app
/create-environment
# Detects: FastAPI + React, monorepo structure
# Generates: Both backend and frontend guides
```

### Go Microservices

```bash
cd go-services
/create-environment
# Detects: Go, gRPC, PostgreSQL
# Generates: Go-specific patterns, microservices architecture
```

## Support

-   **Documentation**: [README.md](../README.md)
-   **Customization Guide**: [CUSTOMIZATION.md](CUSTOMIZATION.md)
-   **Issues**: [GitHub Issues](https://github.com/mderk/memento/issues)
-   **Claude Code Docs**: [Claude Code](https://docs.anthropic.com/en/docs/claude-code)

---

**Happy coding with AI assistance!** 🤖
