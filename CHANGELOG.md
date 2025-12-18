# Changelog

All notable changes to the Memento plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
