# Memento - An AI-Powered Development Environment

> A Claude Code plugin that generates Memory Bank documentation, specialized AI agents, and workflow automation for any project

## Overview

This plugin automatically generates a development environment for your project:

-   **Memory Bank** - Structured documentation system (guides/, workflows/, patterns/)
-   **Specialized AI Agents** - Test runner, developer, code reviewer, design reviewer
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

**Commands:** `/code-review`, `/develop`, `/prime`, `/run-tests`, `/create-prd`, `/create-spec`, `/create-protocol`, `/process-protocol`, `/merge-protocol`, `/update-memory-bank`, `/update-memory-bank-protocol`, `/doc-gardening`

**Agents:** `@test-runner`, `@developer`, `@design-reviewer` (if frontend), `@research-analyst`

**Skills:** `/commit`, `/defer` (backlog), `/load-context`

## Installation

### Prerequisites

-   [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
-   Git (recommended)

### Quick Install

```bash
/plugin marketplace add mderk/memento
/plugin install memento-marketplace@memento
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

See [CHANGELOG.md](CHANGELOG.md) for version history.

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
/update-memory-bank-protocol <protocol-number> # Keep environment updated
```

Generated structure:

```
your-project/
├── CLAUDE.md              # AI assistant entry point
├── .claude/
│   ├── agents/            # Specialized AI agents
│   ├── commands/          # Slash commands
│   └── skills/            # AI skills
└── .memory_bank/          # Documentation hub
    ├── guides/            # Implementation guides
    ├── workflows/         # Development workflows
    └── patterns/          # Code patterns
```

## Documentation

-   [Getting Started Guide](docs/GETTING_STARTED.md) - Walkthrough, workflows, updating, troubleshooting
-   [Protocol Workflow](docs/PROTOCOL_WORKFLOW.md) - PRD → Spec → Protocol → Implementation pipeline and backlog
-   [Customization Guide](docs/CUSTOMIZATION.md) - How to customize your environment
-   [Technical Specification](docs/SPECIFICATION.md) - Architecture and implementation details

## License

MIT License - see [LICENSE](LICENSE) file for details

## Links

-   [GitHub Repository](https://github.com/mderk/memento)
-   [Issues](https://github.com/mderk/memento/issues)
-   [Claude Code Documentation](https://docs.anthropic.com/en/docs/claude-code)
