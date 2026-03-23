# Getting Started with Claude AI Environment

This guide will help you set up an AI development environment in your project in less than 5 minutes.

## Prerequisites

-   **Claude Code CLI** installed
-   **Python 3.10+** (required by plugin skills)
-   **Git** (optional but recommended)
-   **Project directory** with some code (or empty for new project)

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
/memento:create-environment
```

The plugin will ask you questions about your project since it can't detect anything yet.

### For Existing Projects

If you have an existing project:

```bash
cd existing-project
/memento:create-environment
```

The plugin will automatically detect your tech stack and ask for confirmation.

## Step-by-Step Walkthrough

### Example: Django + React Project

```bash
$ cd my-project
$ /memento:create-environment

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
  ✓ Scanned 43 static file entries (manifest.yaml)
  ✓ Evaluated conditionals for your stack
  ✓ Created generation plan: .memory_bank/generation-plan.md

Ready to generate ~60 files. Reply with "Go" to proceed.

$ Go

🚀 Phase 2: Generating files...

📋 Copying static files...
  ✓ Copied .workflows/develop/workflow.py (static)
  ✓ Copied .claude/skills/code-review/SKILL.md (static)
  ... [8 workflows + 10 review competencies + 15 skills]

📦 Generating project-specific documentation...
  ✓ Generated CLAUDE.md (1/18)
  ✓ Generated .memory_bank/README.md (2/18)
  ✓ Generated .memory_bank/product_brief.md (3/18)
  ... [progress continues]
  ✓ Generated .memory_bank/patterns/api-design.md (18/18)

✅ Generation complete!

Generated structure:
  .memory_bank/  (agent documentation)
  .claude/skills/  (15 skills)
  .claude/commands/  (1 command)
  .workflows/  (8 workflow definitions + review competencies)
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
│   ├── commands/
│   │   └── prime.md               # (static) Load context
│   └── skills/                    # All slash commands
│       ├── code-review/           # Parallel competency review
│       ├── develop/               # TDD development workflow
│       ├── run-tests/             # Test runner with coverage
│       ├── commit/                # Git commit with rules
│       ├── create-prd/            # PRD creation
│       ├── create-spec/           # Spec creation
│       ├── create-protocol/       # Protocol creation
│       ├── process-protocol/      # Protocol execution
│       ├── merge-protocol/        # Protocol branch merge
│       ├── update-memory-bank/    # Post-change doc update
│       ├── doc-gardening/         # Memory Bank maintenance
│       ├── defer/                 # Backlog management
│       ├── load-context/          # Protocol context loader
│       ├── design-reviewer/       # (if frontend) UI/UX review
│       └── research-analyst/      # Research and analysis
├── .workflows/                    # Workflow engine definitions
│   ├── develop/                   # TDD workflow (explore → plan → test → implement)
│   ├── code-review/               # Parallel competency review
│   │   └── competencies/          # Review checklists
│   ├── testing/                   # Test execution
│   ├── commit/                    # Commit workflow
│   ├── create-protocol/           # Protocol creation
│   ├── process-protocol/          # Protocol execution
│   ├── merge-protocol/            # Protocol merge
│   └── verify-fix/                # Fix verification
└── .memory_bank/                  # Agent documentation (Memory Bank)
    ├── README.md                  # Navigation hub
    ├── product_brief.md           # Product vision
    ├── tech_stack.md              # Tech details
    ├── guides/
    │   ├── architecture.md
    │   ├── backend.md             # (if backend)
    │   ├── frontend.md            # (if frontend)
    │   ├── visual-design.md       # (if frontend)
    │   ├── testing.md             # Hub: philosophy, pyramid
    │   └── getting-started.md
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

The [`/code-review`][code-review] skill will:

-   Run parallel reviews per competency (architecture, security, performance, etc.)
-   Check code quality and identify issues
-   Synthesize results into a unified report with APPROVE/REQUEST CHANGES recommendation

### 3. Run Tests

Before committing:

```bash
/run-tests
```

The [`/run-tests`][run-tests] skill will:

-   Auto-detect test framework
-   Run tests with coverage analysis
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

After initial setup, use `/memento:update-environment` to keep documentation synchronized with your evolving codebase.

### Smart Detection Mode

```bash
/memento:update-environment auto
```

Detects framework upgrades, new dependencies, database changes, and new plugin features. Recommends which files to update.

### Manual Updates

```bash
/memento:update-environment workflows     # Update all workflow files
/memento:update-environment guides        # Update all guides
/memento:update-environment backend.md    # Update specific file
/memento:update-environment all           # Full regeneration
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
/memento:create-environment

# Option 2: Smart update (preserves local changes)
/memento:update-environment auto
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
2. **Try Skills**: Experiment with [`/prime`][prime], [`/code-review`][code-review], etc.
3. **Customize Guides**: Update project-specific documentation
4. **Share with Team**: Commit `.memory_bank/` and `.claude/` to version control

## Examples by Project Type

### Django API

```bash
cd django-api
/memento:create-environment
# Detects: Django, PostgreSQL, pytest, DRF
# Generates: Backend-focused guides, API patterns
```

### React SPA

```bash
cd react-app
/memento:create-environment
# Detects: React, TypeScript, Jest, Vite
# Generates: Frontend-focused guides, component patterns
```

### Full-Stack Monorepo

```bash
cd fullstack-app
/memento:create-environment
# Detects: FastAPI + React, monorepo structure
# Generates: Both backend and frontend guides
```

### Go Microservices

```bash
cd go-services
/memento:create-environment
# Detects: Go, gRPC, PostgreSQL
# Generates: Go-specific patterns, microservices architecture
```

## Support

-   **Documentation**: [README.md](../README.md)
-   **Protocol Workflow**: [PROTOCOL_WORKFLOW.md](PROTOCOL_WORKFLOW.md) - PRD → Spec → Protocol → Implementation pipeline
-   **Customization Guide**: [CUSTOMIZATION.md](CUSTOMIZATION.md)
-   **Issues**: [GitHub Issues](https://github.com/mderk/memento/issues)
-   **Claude Code Docs**: [Claude Code](https://docs.anthropic.com/en/docs/claude-code)

---

**Happy coding with AI assistance!**

<!-- Skill folders -->
[prime]: ../static/commands/
[code-review]: ../static/skills/code-review/
[run-tests]: ../static/skills/run-tests/
[create-prd]: ../static/skills/create-prd/
[create-spec]: ../static/skills/create-spec/
[develop]: ../static/skills/develop/
[commit]: ../static/skills/commit/
