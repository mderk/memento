# Memento - An AI-Powered Development Environment

> An AI-powered development environment generator with Memory Bank documentation system, specialized agents, and workflow automation

## Overview

This Claude Code plugin automatically generates a development environment for your project, including:

-   **Memory Bank** - Structured documentation system as single source of truth
-   **Specialized AI Agents** - Code reviewer, test runner, and design reviewer
-   **Workflow Automation** - Commands for PRD → Spec → Tasks → Implementation
-   **Tech Stack Agnostic** - Works with any backend/frontend/database combination

## Features

### 🧠 Memory Bank System

-   Organized documentation structure (guides/, workflows/, patterns/)
-   **Dual content system**:
    -   **Prompt-based generation** - LLM adapts content to your tech stack
    -   **Static files** - Universal workflows/checklists copied as-is
-   Auto-detection of project tech stack
-   Mix of project-specific and universal documentation

### 🤖 AI Agents

-   **@code-reviewer** - Automated code quality checks and architectural validation
-   **@test-runner** - Test execution and comprehensive reporting
-   **@design-reviewer** - UI/UX design system compliance and accessibility validation
-   **@research-analyst** - Research and analyze information from web pages, documentation, and project files

### ⚡ Slash Commands

-   `/create-environment` - Initialize AI environment in your project
-   `/update-environment` - Smart update: detect tech stack changes and plugin updates, regenerate affected files
-   `/import-knowledge` - Import external knowledge into project's Memory Bank
-   `/optimize-memory-bank` - Scan and optimize Memory Bank for redundancy
-   `/fix-broken-links` - Validate and fix broken links in Memory Bank
-   `/prime` - Load Memory Bank context
-   `/code-review` - Launch code reviewer agent
-   `/run-tests` - Execute tests with test runner agent
-   `/create-prd` - Generate Product Requirements Document
-   `/create-spec` - Generate Technical Specification
-   `/create-protocol` - Create implementation protocol from PRD/spec
-   `/process-protocol` - Execute protocol steps with AI guidance

### 🛠️ Skills

Skills provide specialized capabilities that Claude can invoke automatically when needed:

-   **detect-tech-stack** - Analyzes project to detect frameworks, databases, test frameworks, and libraries
    -   Scans dependency files (package.json, requirements.txt, go.mod, etc.)
    -   Detects backend/frontend frameworks with versions
    -   Identifies databases, test frameworks, ORMs, UI libraries
    -   Outputs structured JSON for project-analysis.json
    -   Script: `.claude-plugin/skills/detect-tech-stack/scripts/detect.py`

-   **fix-broken-links** - Validates Memory Bank links and fixes broken references
    -   Scans all `.memory_bank/` files for broken links
    -   Checks index.md navigation and cross-references
    -   Automatically fixes or removes broken links
    -   Re-validates after fixes to ensure integrity
    -   Script: `.claude-plugin/skills/fix-broken-links/scripts/validate-memory-bank-links.py`

-   **check-redundancy** - Analyzes documentation for redundant content
    -   Detects repeated phrases and patterns
    -   Calculates redundancy percentage
    -   Reports files exceeding 10% redundancy threshold
    -   Helps maintain concise, high-quality documentation
    -   Script: `scripts/check-redundancy.py`

**Usage**: Skills are invoked automatically by Claude when relevant, or manually via slash commands (`/fix-broken-links`).

## Installation

### Prerequisites

-   [Claude Code](https://code.claude.com/docs/en/setup.md) installed on your machine
-   Git (recommended for version control)

### Quick Install

Add the marketplace and install the plugin:

```bash
/plugin marketplace add mderk/memento
/plugin install memento@memento
```

**Important**: Restart Claude Code after installation for changes to take effect.

### Verify Installation

Check that the plugin is installed:

```bash
/plugin list
```

You should see `memento` in the list. Run `/help` to see available commands.

### Installation Scopes

**User scope** (default - available across all projects):

```bash
/plugin install memento@memento
```

**Project scope** (shared with team via git):

```bash
/plugin install memento@memento --scope project
```

**Local scope** (project-specific, not shared):

```bash
/plugin install memento@memento --scope local
```

### Troubleshooting

-   **Plugin doesn't appear**: Restart Claude Code after installation
-   **Commands not visible**: Run `/help` to verify commands are registered
-   **Need help**: See [Claude Code plugin documentation](https://code.claude.com/docs/en/plugins.md)

### Updating

Update to the latest version:

```bash
/plugin update memento@memento
```

**Auto-updates**: If enabled for the marketplace, the plugin will update automatically at Claude Code startup.

To check your current version:

```bash
/plugin list
```

See [CHANGELOG.md](CHANGELOG.md) for version history and updates.

## Quick Start

1. **Initialize Environment**

    ```bash
    /create-environment
    ```

2. **Two-Phase Generation**

    - **Phase 1**: Planning agent analyzes your project and creates generation plan
    - **Phase 2**: Copies static files + orchestrates per-file generation with specialized agents
    - Detects tech stack from package.json, requirements.txt, etc.
    - Mix of universal workflows (static) and project-specific docs (generated)

3. **Generated Structure**

    ```
    your-project/
    ├── CLAUDE.md              # AI assistant entry point
    ├── .claude/
    │   ├── agents/            # Specialized AI agents
    │   ├── commands/          # Specialized AI commands
    │   └── skills/            # AI agents skills
    └── .memory_bank/          # Documentation hub
        ├── README.md
        ├── product_brief.md
        ├── tech_stack.md
        ├── current_tasks.md
        ├── task-management-guide.md
        ├── guides/            # Implementation guides
        ├── workflows/         # Development workflows
        └── patterns/          # Code patterns
    ```

4. **Start Using**
    ```bash
    /prime                     # Load context
    /create-prd "new feature description"  # Create PRD
    .....
    /create-spec prd-file      # Create spec if you need more details than PRD provides
    /create-protocol prd-file spec-file <or anything agent can derive PRD from> # Generate tasks
    /process-protocol <protocol-number> [<step-number>] [<additional-instructions>] # Execute tasks from protocol
    ```

5. **Keep Environment Updated**
    ```bash
    # Smart update: detect changes and get recommendations
    /update-environment auto

    # Update specific files after tech stack changes
    /update-environment workflows

    # Update single file
    /update-environment backend.md
    ```

## Documentation

-   [Getting Started Guide](docs/GETTING_STARTED.md) - Quick start and setup
-   [Customization Guide](docs/CUSTOMIZATION.md) - How to customize your environment
-   [Technical Specification](docs/SPECIFICATION.md) - Architecture and implementation details

**Archive** (development history):

-   [Product Requirements](docs/archive/PRD.md)
-   [Implementation Plan](docs/archive/IMPLEMENTATION_PLAN.md)
-   [Research Report](docs/archive/RESEARCH_REPORT.md)

## Use Cases

-   **New Projects**: Set up AI development environment from scratch
-   **Existing Projects**: Add AI-powered documentation and workflow automation
-   **Team Onboarding**: Standardize development practices across team
-   **Documentation**: Keep project documentation synchronized with code

## Keeping Your Environment Updated

After initial setup, use `/update-environment` to keep documentation synchronized with your evolving codebase:

### Smart Detection Mode

Automatically detect tech stack changes and plugin updates:

```bash
/update-environment auto
```

**What it detects:**
- Framework upgrades (Django 4 → 5, React 17 → 18)
- New frameworks added (added Playwright, Cypress)
- Database changes (PostgreSQL → MongoDB)
- New plugin features (new agents, commands, workflows)

**Example output:**
```
Tech Stack Changes Detected:
- Playwright added (E2E testing framework)
- Django 4.2 → 5.1 (version bump)

Plugin Updates Detected:
- research-analyst.md (NEW agent available)

Recommendations:
A: Update 3 affected files
B: Add 1 new agent
C: Both (4 files total)
D: Full regeneration

Your choice?
```

### Manual Updates

Update specific files or categories:

```bash
# Update all workflow files
/update-environment workflows

# Update all guides
/update-environment guides

# Update specific file
/update-environment backend.md

# Update multiple files
/update-environment testing.md, backend.md, frontend.md

# Full regeneration
/update-environment all
```

### When to Update

**Recommended scenarios:**
- ✅ After `npm install` / `pip install` (new dependencies)
- ✅ After framework upgrades (React, Django, etc.)
- ✅ After adding test frameworks (Playwright, Vitest)
- ✅ After plugin updates (check with `/update-environment detect`)
- ✅ Monthly maintenance (run `auto` to check for drift)

**Examples:**

```bash
# After adding Playwright
npm install -D @playwright/test
/update-environment auto  # Detects Playwright, updates testing.md

# After Django upgrade
pip install django==5.1
/update-environment auto  # Detects version change, updates backend.md

# After plugin update
/plugin update memento@memento
/update-environment detect  # Check for new features
```

## Requirements

-   Claude Code CLI
-   Git (recommended for version control)

## How It Works

1. **Phase 1 - Planning**: Planning agent scans project config files and creates generation plan with project analysis
2. **Phase 2 - Generation**:
    - **Static files**: Universal workflows/checklists copied directly (no LLM)
    - **Prompt-based**: One agent per file generates project-specific content
3. **Detection**: Identifies frameworks, libraries, and project structure from package.json, requirements.txt, go.mod, etc.
4. **Conditional logic**: Both static and prompt files use conditionals (e.g., "only for React projects")
5. **Adaptation**: Mix of universal best practices (static) and stack-specific content (generated)

## Examples

### Django + React Project

```bash
/create-environment
# Detected: Django, React, PostgreSQL, pytest, jest
# Static: Universal workflows (development-workflow, code-review-checklist)
# Generated: Django-specific backend guide, React component patterns, API design patterns
```

### FastAPI + Vue Project

```bash
/create-environment
# Detected: FastAPI, Vue, PostgreSQL, pytest, vitest
# Static: Universal workflows (development-workflow, protocol workflows)
# Generated: FastAPI async patterns, Vue composition API guide, Pydantic schemas
```

### Go Microservices

```bash
/create-environment
# Detected: Go, gRPC, PostgreSQL
# Static: Universal workflows and checklists
# Generated: Go-specific patterns, microservices architecture, testing with testing package
```

## Contributing

Contributions are welcome! Please read our contributing guidelines.

## License

MIT License - see [LICENSE](LICENSE) file for details

## Links

-   [GitHub Repository](https://github.com/mderk/memento)
-   [Documentation](docs/)
-   [Issues](https://github.com/mderk/memento/issues)
-   [Claude Code Documentation](https://code.claude.com/docs)

---

**Generated with Claude AI Environment** 🤖
