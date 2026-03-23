# Memento - An AI-Powered Development Environment

> A Claude Code plugin that generates Memory Bank documentation, skills, and workflow automation for any project

## Overview

This plugin automatically generates a development environment for your project:

-   **Memory Bank** - Structured documentation system (guides/, workflows/, patterns/)
-   **Skills & Commands** - Commit, code review, develop, test runner, design reviewer
-   **Workflow Automation** - PRD → Spec → Protocol → Implementation pipeline
-   **Tech Stack Agnostic** - Works with any backend/frontend/database combination

## Features

### Plugin Commands (namespaced)

-   `/memento:create-environment` - Initialize AI environment in your project
-   `/memento:update-environment` - Smart update: detect tech stack changes, regenerate affected files
-   `/memento:import-knowledge` - Import external knowledge into project's Memory Bank
-   `/memento:optimize-memory-bank` - Scan and optimize Memory Bank for redundancy
-   `/memento:fix-broken-links` - Validate and fix broken links in Memory Bank

### What Gets Deployed to Your Project

After running `/memento:create-environment`, your project gets:

**Skills (slash commands):**

| Skill | Description |
|-------|-------------|
| `/prime` | Load Memory Bank context into conversation |
| `/develop` | TDD development workflow (explore → plan → test → implement → verify) |
| `/code-review` | Parallel competency-based review (architecture, security, performance, etc.) |
| `/run-tests` | Run tests with coverage analysis |
| `/commit` | Stage and commit with well-formatted message |
| `/create-prd` | Generate Product Requirements Document |
| `/create-spec` | Generate technical specification from PRD |
| `/create-protocol` | Create execution plan with step files from PRD/spec |
| `/process-protocol` | Execute protocol steps in isolated git worktrees |
| `/merge-protocol` | Merge protocol branch with code review |
| `/update-memory-bank` | Update Memory Bank docs after code changes |
| `/doc-gardening` | Memory Bank maintenance (links, redundancy, freshness) |
| `/defer` | Defer out-of-scope findings to backlog |
| `/load-context` | Load protocol context files into conversation |
| `/design-reviewer` | UI/UX design review (if frontend) |
| `/research-analyst` | Research and analyze information from docs/web |

**Workflow engine** (`memento-workflow` plugin) drives `/develop`, `/code-review`, `/commit`, `/process-protocol`, `/merge-protocol`, and `/create-protocol` as stateful, resumable workflows with checkpoints.

## Installation

### Prerequisites

-   [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
-   Python 3.10+ (required by workflow engine)
-   Git (recommended)

### Quick Install

```bash
/plugin marketplace add mderk/memento
/plugin install memento-marketplace@memento
/plugin install memento-marketplace@memento-workflow
```

Restart Claude Code after installation.

### Installation Scopes

```bash
/plugin install memento-marketplace@memento                # User scope (default, all projects)
/plugin install memento-marketplace@memento --scope project # Project scope (shared via git)
/plugin install memento-marketplace@memento --scope local   # Local scope (not shared)
```

### Updating

```bash
/plugin update memento-marketplace@memento
```

See [CHANGELOG.md](../CHANGELOG.md) for version history.

### File Access Permissions

During generation, Claude Code requests permission to read plugin template files. To reduce prompts, add to `.claude/settings.json`:

```json
{
    "permissions": {
        "allow": ["Read(~/.claude/plugins/**)"]
    }
}
```

## Quick Start

```bash
/memento:create-environment      # Generate environment (two-phase: plan → generate)
/prime                           # Initialize context
/create-prd "feature description" # Create PRD
/create-spec prd-file            # Create spec if needed
/create-protocol prd-file/spec-file/ general-instructions # Generate an execution plan with tasks and step files
/process-protocol <number>       # Execute tasks in an isolated git worktree with quality checks
/code-review                      # Review the code
/commit                           # Commit the changes
/merge-protocol                   # Merge the protocol branch
/update-memory-bank <protocol-path> # Keep environment updated
```

Generated structure:

```
your-project/
├── CLAUDE.md              # AI assistant entry point
├── .claude/
│   ├── commands/          # /prime command
│   └── skills/            # All slash commands (develop, code-review, commit, etc.)
├── .workflows/            # Workflow engine definitions (develop, code-review, commit, etc.)
│   └── code-review/
│       └── competencies/  # Review checklists (architecture, security, testing, etc.)
└── .memory_bank/          # Agent documentation (Memory Bank)
    ├── guides/            # Implementation guides
    └── patterns/          # Code patterns
```

## Documentation

-   [Getting Started Guide](docs/GETTING_STARTED.md) - Walkthrough, workflows, updating, troubleshooting
-   [Protocol Workflow](docs/PROTOCOL_WORKFLOW.md) - PRD → Spec → Protocol → Implementation pipeline and backlog
-   [Customization Guide](docs/CUSTOMIZATION.md) - How to customize your environment
-   [Technical Specification](docs/SPECIFICATION.md) - Architecture and implementation details

## Dependencies

This plugin requires the [memento-workflow](../memento-workflow/) plugin for workflow commands (`create-environment`, `update-environment`).

## License

MIT License - see [LICENSE](../LICENSE) file for details

## Links

-   [GitHub Repository](https://github.com/mderk/memento)
-   [Issues](https://github.com/mderk/memento/issues)
-   [Claude Code Documentation](https://docs.anthropic.com/en/docs/claude-code)
