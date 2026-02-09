# Getting Started with Claude AI Environment

This guide will help you set up an AI development environment in your project in less than 5 minutes.

## Prerequisites

-   **Claude Code CLI** installed
-   **Git** (optional but recommended)
-   **Project directory** with some code (or empty for new project)

**Note**: No Python or external dependencies required! Generation is powered by the LLM.

## Installation

### Step 1: Install the Plugin

```bash
claude plugin install memento
```

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

📝 Scanning generation prompts...
  ✓ Scanned 38 prompt files (frontmatter only)
  ✓ Evaluated conditionals for your stack
  ✓ Created generation plan: .memory_bank/generation-plan.md

Ready to generate 38 files. Reply with "Go" to proceed.

$ Go

🚀 Phase 2: Generating files...

📦 Generating documentation...
  ✓ Generated CLAUDE.md (1/38)
  ✓ Generated .memory_bank/README.md (2/38)
  ✓ Generated .memory_bank/product_brief.md (3/38)
  ... [progress continues]
  ✓ Generated .claude/commands/create-spec.md (35/35)

✅ Generation complete!

Generated structure:
  .memory_bank/  (28 files)
  .claude/agents/  (3 agents)
  .claude/commands/  (7 commands)
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
│   │   ├── test-runner.md
│   │   └── design-reviewer.md
│   └── commands/
│       ├── prime.md
│       ├── code-review.md
│       ├── run-tests.md
│       ├── create-prd.md
│       └── create-spec.md
└── .memory_bank/
    ├── README.md                  # Navigation hub
    ├── product_brief.md           # Product vision
    ├── tech_stack.md              # Tech details
    ├── current_tasks.md           # Task tracking
    ├── task-management-guide.md
    ├── guides/
    │   ├── index.md
    │   ├── ai-agent-handbook.md
    │   ├── architecture.md
    │   ├── backend.md
    │   ├── frontend.md
    │   ├── testing.md
    │   ├── visual-design.md
    │   ├── getting-started.md
    │   └── code-review-guidelines.md
    ├── workflows/
    │   ├── index.md
    │   ├── development-workflow.md
    │   ├── agent-orchestration.md
    │   ├── code-review-workflow.md
    │   ├── testing-workflow.md
    │   ├── bug-fixing.md
    │   ├── feature-development.md
    │   ├── create-prd.md
    │   ├── create-spec.md
    │   ├── create-protocol.md
    │   └── process-protocol.md
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

# Option 2: Merge mode
/create-environment --merge
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
-   **Issues**: [GitHub Issues](https://github.com/yourusername/memento/issues)
-   **Claude Code Docs**: [code.claude.com/docs](https://code.claude.com/docs)

---

**Happy coding with AI assistance!** 🤖
