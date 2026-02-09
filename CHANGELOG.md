# Changelog

All notable changes to the Memento plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-02-07

### Added

-   **`/update-memory-bank` command**: Ad-hoc Memory Bank update after code changes
-   **`/update-memory-bank-protocol` skill**: Post-protocol Memory Bank update running in isolated `context: fork`
    -   Collects findings from all step files, triages, transforms, and applies to Memory Bank
    -   References workflow for rules, avoids content duplication
-   **Findings system**: Two-level discovery capture during protocol execution
    -   `## Findings` section in step files (task-local)
    -   `_context/findings.md` for promoted system-level findings
    -   Tags: `[DECISION]`, `[GOTCHA]`, `[REUSE]`
-   **Protocol mode** in development workflow: Streamlined mode for protocol subtasks
    -   Skips code review (done separately by caller)
    -   Skips Memory Bank update and user report
    -   Returns modified files list + discoveries to caller
-   **`develop` branch setup**: One-time creation with user choice of base branch in process-protocol

### Changed

-   **`process-protocol.md`**: Major restructuring
    -   Worktree-based execution with configurable branching strategies
    -   Explicit context passing to sub-agents (text + file paths)
    -   Step 2 lists `_context/` paths without reading (sub-agents read if needed)
    -   Step 3 ensures `develop` branch exists before worktree creation
    -   Step 4 passes Task, Key context, and Reference files explicitly
    -   Protocol Completion invokes `/update-memory-bank-protocol` skill
    -   `.env` file copying after worktree creation
-   **`development-workflow.md`**: Added Mode section (standalone vs protocol) with inline reminders per phase
-   **`update-memory-bank.md`**: Expanded with distillation pipeline
    -   "What NOT to Update" rules unified at top
    -   "Check Existing Content" promoted to standard process Step 3
    -   "After Protocol Completion" section: Collect → Triage → Transform → Apply → Mark
-   **`create-protocol.md`**: Step file template now includes `## Findings` and `_context/findings.md` description
-   **`git-worktree-workflow.md`**: Replaced `cd /path/to/project` with `${PROJECT_ROOT}`, fixed stale process-protocol references
-   **`merge-protocol.md`**: Sets status to Complete, reminds about `/update-memory-bank-protocol`
-   **`migrate-protocol.md`**: Restructured as procedural steps (Pre-flight → Detect → Analyze → Migrate → Verify → Report), added `## Findings` to migration, dry-run support
-   **`manifest.yaml`**: Added update-memory-bank command and update-memory-bank-protocol skill

### Removed

-   **`develop-protocol.md`**: Replaced by development workflow's protocol mode

---

## [1.0.5] - 2026-01-22

### Fixed

-   **Plugin manifest**: Removed invalid `commands`, `agents`, `skills` path fields from `plugin.json`
    -   Claude Code doesn't support string paths for these fields
    -   Plugin now uses auto-discovery from standard directories
    -   Fixes "Invalid input" validation errors preventing plugin from loading

---

## [1.0.4] - 2026-01-19

### Changed

-   **`code-reviewer.md.prompt`**: Major refactoring
    -   Reduced from 150-250 lines to 50-80 lines (concise, references workflow)
    -   Changed model from `opus` to `sonnet`
    -   Removed MCP tools - now uses only basic read/git tools
    -   Added Critical Restrictions section (read-only agent)
    -   Single-line description format for YAML parsing
    -   Follows test-runner.md pattern structure
    -   Stack-specific sections moved to code-review-guidelines.md

---

## [1.0.3] - 2026-01-18

### Added

-   **Developer Agent** (`agents/developer.md`): New agent for writing code based on provided context and task description
-   **`/develop` Command**: Execute development tasks using the developer sub-agent
-   **`analyze-local-changes` Skill**: Analyze local modifications in Memory Bank files
    -   Computes MD5 hashes and compares with stored hashes
    -   Classifies changes for auto-merge vs manual review
    -   Provides structured output for merge operations
-   **`CLAUDE.md.prompt`**: New prompt template for generating minimal root onboarding file
-   **`update-memory-bank.md.prompt`**: New prompt for Memory Bank update workflow
-   **Multiple Backends Support**: Projects with multiple backend technologies now generate:
    -   `backend.md` as an index file
    -   Separate `backend-{framework}.md` for each backend (e.g., `backend-fastapi.md`, `backend-nextjs.md`)
-   **New Static Workflows**:
    -   `testing-workflow.md`: Universal testing workflow
    -   `update-memory-bank.md`: Workflow for updating Memory Bank
    -   `code-review-workflow.md`: Code review process
    -   `develop-protocol.md`: Development protocol for sub-agents

### Changed

-   **`update-environment.md`**: Significantly expanded with smart update functionality and local changes detection
-   **`create-environment.md`**: Improved generation process
-   **`development-workflow.md`**: Major expansion with detailed development process
-   **`create-protocol.md`**: Updated protocol structure
-   **`process-protocol.md`**: Enhanced task processing logic
-   **`backend.md.prompt`**: Added multiple backends logic and index file generation
-   **`README.md.prompt`**: Updated structure, removed current_tasks.md reference
-   **Skills documentation**: Added explicit invocation commands to all skills
-   **`anti-patterns.md`**: Removed hardcoded project names
-   **Agent definitions**: Moved `test-runner` from prompt to static file

### Removed

-   **Prompt templates** (moved to static or removed as redundant):
    -   `current_tasks.md.prompt`: Removed (task management simplified)
    -   `task-management-guide.md.prompt`: Removed (consolidated into workflows)
    -   `feature-development.md.prompt`: Removed (covered by development-workflow)
    -   `testing-workflow.md.prompt`: Moved to static
    -   `CLAUDE.md.prompt` from memory_bank: Moved to root prompts directory

---

## [1.0.2] - 2025-12-27

### Changed

-   **`create-environment.md`**: Enhanced prompt template handling and content generation instructions
-   **`update-environment.md`**: Improved update process with detailed prompt handling

---

## [1.0.1] - 2025-12-27

### Added

-   **`detect-tech-stack` Skill**: Automatic detection of project tech stack
    -   Analyzes package.json, requirements.txt, go.mod, etc.
    -   Returns structured JSON with detected frameworks, databases, libraries
-   **Smart Update System**: Intelligent environment updates based on tech stack changes

### Changed

-   **`update-environment.md`**: Major expansion (+325 lines) with smart update functionality
-   **`create-environment.md`**: Improved generation process
-   **Static file scanning**: Added mandatory workflows
-   **Documentation**: Updated SPECIFICATION.md, GETTING_STARTED.md, CUSTOMIZATION.md

### Removed

-   **`code-review-checklist.md`**: Removed from static guides (consolidated elsewhere)

---

## [1.0.0] - 2025-11-25

### Added

-   **Dual Content System**: Combines prompt-based generation with static file copying

    -   35 prompt files that generate project-specific documentation
    -   4 static files with universal workflows copied as-is
    -   Conditional logic for both prompts and static files via `manifest.yaml`

-   **Memory Bank System**: Structured documentation hub

    -   Core files: `product_brief.md`, `tech_stack.md`, `current_tasks.md`
    -   Guides directory: Implementation guides (architecture, backend, frontend, testing, etc.)
    -   Workflows directory: Development processes and protocols
    -   Patterns directory: Code patterns and best practices

-   **AI Agents**:

    -   `@code-reviewer`: Automated code quality checks and architectural validation
    -   `@test-runner`: Test execution and comprehensive reporting
    -   `@design-reviewer`: UI/UX design system compliance and accessibility validation

-   **Slash Commands**:

    -   `/create-environment`: Initialize AI environment in your project
    -   `/import-knowledge`: Import external knowledge into project's Memory Bank
    -   `/prime`: Load Memory Bank context
    -   `/code-review`: Launch code reviewer agent
    -   `/run-tests`: Execute tests with test runner agent
    -   `/create-prd`: Generate Product Requirements Document
    -   `/create-spec`: Generate Technical Specification
    -   `/generate-tasks`: Break down PRD into actionable tasks
    -   `/process-tasks-list`: Execute task list

-   **Tech Stack Detection**: Auto-detects project configuration from:

    -   `package.json` (JavaScript/TypeScript)
    -   `requirements.txt`, `pyproject.toml` (Python)
    -   `go.mod` (Go)
    -   `Gemfile` (Ruby)
    -   And other common config files

-   **Documentation**:
    -   Getting Started Guide
    -   Customization Guide
    -   Technical Specification
    -   Installation and update instructions

### Features

-   Two-phase generation process (Planning → Execution)
-   Tech stack agnostic (works with any backend/frontend/database combination)
-   Semantic analysis for knowledge import
-   Mix of universal and project-specific documentation
-   Git-friendly structure for team sharing
