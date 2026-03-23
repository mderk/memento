# Changelog

All notable changes to the Memento plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [memento 2.0.1, memento-workflow 1.0.1] - 2026-03-23

### Changed

- **Skill frontmatter**: trimmed bloated `<example>` blocks from `research-analyst` and `design-reviewer` descriptions (~350 tokens saved per session)
- **Skill frontmatter**: fixed `model: fork` → `context: fork` (correct Claude Code syntax)
- **MCP tool descriptions**: converted `submit` and `next` Args docstrings to `Annotated` types, trimmed `open_dashboard` verbose description
- **MCP tool `shell_log`**: marked as "Debug only — bloats context" across `start`, `submit`, `next`
- **CHANGELOG.md**: moved from `memento/` to repo root (shared across both plugins)

## [2.0.0] - 2026-03-23

Complete rework. 120 commits, 328 files changed, +49k lines.

### Workflow Engine

New `memento-workflow` plugin — a stateful MCP-based workflow engine that drives all orchestration. Replaces LLM-scripted command prompts with declarative workflow definitions.

- **9 block types**: ShellStep, LLMStep, PromptStep, GroupBlock, LoopBlock, RetryBlock, ConditionalBlock, SubWorkflow, ParallelEachBlock
- **State machine**: advance/submit cycle with checkpoints and resume from crash
- **Parallel execution**: concurrent lanes with auto-advance for shell-only paths
- **Inline SubWorkflow**: child runs with transparent proxying through parent run_id
- **Dry-run preview**: `start(dry_run=True)` returns hierarchical tree of all steps without executing anything. Uses `AdvanceHook` pattern — state machine has no dry-run knowledge
- **Dashboard**: web UI for browsing runs, viewing artifacts, comparing executions
- **670+ tests** covering all block types, resume, idempotency, edge cases

### All orchestration is now engine-driven

`/commit`, `/code-review`, `/develop`, `/process-protocol`, `/merge-protocol`, `/create-protocol` — all rewritten as workflow engine workflows. LLM acts as a relay, executing actions returned by the engine. Benefits: deterministic flow, resumable from checkpoint, parallel reviews, auto-advancing shell steps.

### Plugin split

New `memento-workflow` plugin provides the engine as an MCP server. Workflow definitions (commit, code-review, develop, etc.) stay in `memento` and call the engine via MCP tools.

### Prompt and static consolidation

- Commands and agents converted to skills (design-reviewer, research-analyst, commit, defer, load-context)
- ~15 prompt templates replaced with static files — agents, commands, workflows that don't need per-project adaptation
- Deduplicated product_brief, tech_stack, architecture prompts
- README prompt slimmed to 25-35 lines

### Developer tooling

- pyright and ruff integrated as dev dependencies with CI enforcement
- Protocol-based development in git worktrees with structured code review
- Halt directives, file-based data exchange, structured output validation
- Coverage stagnation detection in TDD loops

## [1.6.0] - 2026-02-25

### Added

-   **`pre-update` command** in `analyze.py`: Comprehensive pre-update check combining all Step 0 detection into one call — local changes, source changes, prompt scanning, manifest classification, obsolete detection, tech-stack diff
-   **`copy-static` command** in `analyze.py`: Copy all applicable static files in one call with integrated 3-way merge for conflict-free cases, `--filter` categories, `--base-commit` for merge mode
-   **`merge --write` flag**: When merge succeeds (no conflicts), script writes merged content directly to target file — saves LLM from reading merge JSON + writing file separately
-   **Conditional evaluator**: Evaluate manifest.yaml/frontmatter expressions (`&&`, `||`, `!`, `==`, bool lookup) against project-analysis.json
-   **Frontmatter parser**: Parse `.prompt` file YAML frontmatter without PyYAML dependency
-   **Manifest parser**: Parse `static/manifest.yaml` line-by-line with conditional handling
-   **Static file classifier**: Decision-matrix classification (new/safe_overwrite/local_only/merge_needed/up_to_date/skipped_conditional)
-   **Tech stack comparator**: Compare old vs new project analyses with high/medium/low impact classification
-   **Obsolete file detector**: Find generation-plan entries with no matching plugin source
-   **163 new tests**: Full coverage for all new functions, commands, parsers, and edge cases; `pytest-cov` added as dev dependency
-   **100% coverage enforcement rule**: Changed files must reach 100% line coverage — added to testing workflow, testing hub prompt, backend/frontend testing prompts, and code review testing competency (CRITICAL severity)
-   **Coverage flags table**: Framework-specific coverage flags (pytest, jest, vitest, go test, rspec) in testing workflow and backend testing prompt

### Changed

-   **`update-environment.md`**: Step 0.2 replaced 3+ separate detection calls with single `pre-update` call; Step 4A replaced manual static file handling with single `copy-static` call; Step 4B uses `merge --write`
-   **`create-environment.md`**: Phase 2 step 2 uses `copy-static` for static files instead of manual copying
-   **`analyze-local-changes/SKILL.md`**: Added Mode 10 (Pre-Update Check) and Mode 11 (Copy Static Files) documentation; updated Mode 6 with `--write` flag
-   **`static/skills/commit/SKILL.md`**: Bumped to v1.1.0, added "CRITICAL: Bash Execution Rules" section (separate Bash calls per git command), reformatted bullets, removed `bash` from code fence language hints
-   **`testing-workflow.md`**: Added coverage flags table, coverage enforcement in Step 3 analysis, per-changed-file coverage section in report template
-   **`testing.md.prompt`**: Added "Hard rule — changed files get 100% coverage" to Coverage Goals
-   **`review/testing.md.prompt`**: Added changed-file 100% coverage to "Coverage matches risk" rule, marked as CRITICAL severity
-   **`testing-backend.md.prompt`**: Added coverage flags table by framework, enforcement note, `--cov-report=term-missing`
-   **`testing-frontend.md.prompt`**: Added coverage enforcement note
-   **`update-plan` auto-add and `--remove`**: New files are auto-inserted into the correct plan section (Guides, Workflows, etc.); `--remove` flag deletes obsolete rows
-   **Defer skill**: Added `area`/`effort` fields, list filters (`--type`, `--area`, `--priority`, `--effort`), `view` command for grouped dashboards, inline-comment stripping in frontmatter parsing

### Fixed

-   **`get_all_mb_files()` scans all file types**: Previously only scanned `*.md`, causing non-markdown files (`defer.py`, `load-context.py`) to be falsely reported as "missing" by `detect`
-   **Documentation audit**: Fixed plugin command namespacing, outdated counts, SPECIFICATION version, CUSTOMIZATION .gitignore advice; added Python 3.10+ prerequisite, PROTOCOL_WORKFLOW.md
-   **`analyze-local-changes` skill usage**: Fixed skill invocation patterns

## [1.5.0] - 2026-02-20

### Added

-   **`/doc-gardening`** (command + workflow): Memory Bank maintenance entrypoint — link integrity, redundancy, freshness, knowledge promotion
-   **`/update-memory-bank-protocol`** (command): Post-protocol Memory Bank update from Findings (promoted from skill to command)
-   **`AGENTS.md`** wrapper: Thin redirect to `CLAUDE.md` so all agents load the same rules
-   **Harness tests**: `test_readme_prompt_is_a_map_not_a_manual`, `test_agents_wrappers_point_to_claude_md`, `test_shipped_templates_use_namespaced_gardening_commands`

### Changed

-   **Namespaced gardening commands**: shipped docs reference `/memento:fix-broken-links` and `/memento:optimize-memory-bank` instead of thin local wrappers
-   **README.md.prompt**: Slimmed from 200-400 → 120-220 line target ("map, not manual"); removed verbose examples, simplified directory tree
-   **CLAUDE.md**: Added "What matters", "Golden commands", "Mechanical invariants" sections; removed `scripts/` from directory tree
-   **Skill script paths**: All four skills (`analyze-local-changes`, `check-redundancy`, `detect-tech-stack`, `fix-broken-links`) now use `${CLAUDE_PLUGIN_ROOT}/skills/…/scripts/` absolute paths instead of broken relative `./scripts/` references
-   **Post-generation validation**: `create-environment` Phase 3 and `update-environment` Step 5 now run `/memento:fix-broken-links` (mandatory) and verify merge stats inline
-   **Dev command rename**: `/import-knowledge` → `/import-knowledge-into-plugin` to avoid confusion with `/memento:import-knowledge`

### Removed

-   **`commands/fix-broken-links.md`**: Thin wrapper deleted — `/memento:fix-broken-links` is the only entry point
-   **`static/skills/update-memory-bank-protocol/`**: Promoted to `static/commands/update-memory-bank-protocol.md`
-   **`scripts/`** directory: Deleted `validate-links.py` (superseded by skill), `check-redundancy.py` (identical dead copy), and `README.md`

## [1.4.0] - 2026-02-20

### Added

-   **3-way merge system** in `analyze-local-changes`:
    -   Section-level 3-way merge (`merge` command) using Generation Base as common ancestor
    -   Two-commit system (`commit-generation` command): Generation Base (clean plugin output) + Generation Commit (after merge)
    -   Preserves user-added sections and local modifications across repeated `/update-environment` runs
    -   Conflict detection: `both_modified`, `plugin_removed_user_modified`, `both_added`, `user_deleted`
    -   Anchor-based positioning for user-added sections in merged output
-   **Protocol completeness review competency** (`review/protocol-completeness.md`): Document-specific review for protocols and specs
    -   Implementability, cross-step consistency, edge case coverage, missing pieces checklist

### Changed

-   **Prompt→static conversion**: Converted 15 prompt-based files (agents, commands, workflows) to static files for direct deployment without LLM generation
    -   Agents: `design-reviewer`, `developer`, `research-analyst`
    -   Commands: `create-prd`, `create-spec`, `create-protocol`, `process-protocol`, `prime`, `run-tests`, `develop`
    -   Workflows: `index`, `bug-fixing`, `agent-orchestration`, `create-prd`, `create-spec`
    -   Skill: `commit/SKILL.md`
-   **`README.md`**: Condensed to focused quick-reference
-   **`CLAUDE.md`**: Rewritten as concise developer guide
-   **`SPECIFICATION.md`**: Updated to reflect current architecture (prompt counts, static counts, merge system)
-   **`GETTING_STARTED.md`**: Fixed progress counters (18 prompt files, not 33) and static file counts
-   **`CUSTOMIZATION.md`**: Removed nonexistent `plugin-config.json` section and `/sync-docs` reference, fixed GitHub URLs, updated regeneration docs to describe Phase 0 options
-   **`manifest.yaml`**: Added `review/protocol-completeness.md`, new static agents/commands/workflows/skills

### Removed

-   **15 prompt templates**: Replaced by static files (see Changed above)
-   **`agents/developer.md`**, **`commands/develop.md`**, **`skills/commit/SKILL.md`**: Moved to `static/`
-   **`docs/archive/`**: Removed archived planning documents (IMPLEMENTATION_PLAN, PRD, RESEARCH_REPORT)

---

## [1.3.0] - 2026-02-13

### Added

-   **Backlog system** (`/defer` skill): Structured deferred work tracking
    -   `defer.py` script: create, close, list, link-finding operations with JSON output
    -   Automatic `.backlog/` scaffolding (items/, archive/, templates/)
    -   Integration with protocol steps via `[DEFER]` tags in Findings sections
    -   Priority levels (p0-p3), types (bug, debt, idea, risk), lifecycle (open → scheduled → closed)
    -   Added to `manifest.yaml` for deployment to generated projects
-   **Testing code review competency** (`review/testing.md.prompt`): Project-specific test quality rules
    -   Conditional generation based on detected test stack (pytest, jest, vitest, rspec, go test)
    -   Framework-specific subsections with actual tool names
    -   E2E subsections for Playwright or Cypress (only if detected)
    -   Anti-patterns table, severity guidance, coverage-matches-risk rules
-   **Hub-and-spoke testing documentation**: Split monolithic testing guide into focused files
    -   `testing-backend.md.prompt` — backend frameworks, fixtures, API testing, factories, mocking
    -   `testing-frontend.md.prompt` — frontend frameworks, component testing, E2E, hooks, stores
    -   `testing.md.prompt` refactored as concise hub (philosophy, pyramid, best practices only)
-   **Package manager detection** in `detect-tech-stack`:
    -   Detects Python runners (uv, poetry, pipenv, pip) and Node runners (yarn, pnpm, npm) from lockfiles
    -   Generates correct run commands (`uv run pytest`, `yarn test`, `yarn playwright test`, etc.)
    -   New `package_managers` and `commands` objects in project-analysis.json output
-   **Anti-Pattern #26**: Hallucinated Project-Specific Code — detecting and preventing invented model fields, import paths, and API endpoints in generated docs

### Changed

-   **`detect.py`**: Major refactoring
    -   Dynamic subdirectory discovery (`_discover_subdirs`) replaces hardcoded dir list
    -   Merged dependency collection across all subdirs (`_collect_all_deps`)
    -   Package manager detection from lockfiles with fallback logic
    -   Command generation based on detected runners + test frameworks
-   **`code-review.md`** (static command):
    -   Added testing competency auto-detection (`*test*`, `*spec*` file patterns)
    -   Improved review prompt: diff-focused review, pre-existing issue flagging (`[PRE-EXISTING]`)
    -   Added finding triage requirement (FIX / DEFER / ACCEPT verdict per finding)
-   **`SCHEMA.md`**: Added `package_managers` and `commands` objects to schema
-   **`environment-generator.md`**: Added rules for pattern-based code examples and command variables
-   **`anti-patterns.md`**: Added Anti-Pattern #26 with detection rules and examples
-   **Testing prompts**: All testing prompts now use `{commands.*}` variables instead of hardcoded commands, and show framework patterns with generic entity names (Item, Button) instead of project-specific hallucinated names
-   **`code-review-workflow.md`** (static): Restructured competency tables
    -   Testing competency moved from project-specific to universal
    -   Added document-specific competency section with protocol-completeness
    -   Updated competency selection guidance for behavior changes and protocol docs
    -   Reformatted finding triage table for readability
-   **`process-protocol.md`** (static): Minor process updates
-   **Prompt link updates**: README.md, index.md, backend.md, frontend.md, update-memory-bank.md prompts updated to reference hub-and-spoke testing files
-   **`manifest.yaml`**: Added `/defer` skill (SKILL.md + defer.py)

---

## [1.2.0] - 2026-02-09

### Added

-   **Competency-based review system**: Specialized review checklists per quality dimension
    -   5 universal competencies (static): architecture, security, performance, data-integrity, simplicity
    -   1 project-specific competency (prompt-based, conditional): testing
    -   2 language-specific competencies (static, conditional): typescript, python
    -   Each competency file: rules, anti-patterns table, severity guidance
-   **`/code-review` command** (static): Orchestrates parallel sub-agents per competency
    -   Auto-detects relevant competencies from changed file patterns
    -   Spawns parallel Task sub-agents, each focused on one quality dimension
    -   Synthesizes results into unified report with APPROVE/REQUEST CHANGES recommendation
-   **`/load-context` skill**: Loads protocol context files into agent conversation
    -   Python script scans `_context/` directories for protocol and group context

### Changed

-   **`process-protocol.md`**: Simplified context loading via `/load-context`, inline context in step files
-   **`create-protocol.md`**: Streamlined step file template structure
-   **`git-worktree-workflow.md`**: Major reduction — removed redundant sections
-   **`merge-protocol.md`**: Simplified procedure
-   **`development-workflow.md`**: Phase 4 uses `/code-review` command instead of `@code-reviewer` agent
-   **`code-review-workflow.md`**: Restructured around competency system
    -   Added Review Competencies section with tables and selection guide
    -   Added Output Format for per-competency and synthesized reports
    -   Process references `/code-review` command instead of `@code-reviewer` agent
-   **`code-review-guidelines.md.prompt`**: Slimmed down, removed overlap with competency files
    -   Generic checklists (security, performance, architecture) moved to competency files
    -   Kept project-specific: philosophy, severity levels, feedback process, framework-specific notes
    -   Reduced target length from 300-400 to 200-300 lines
-   **`ai-agent-handbook.md.prompt`**: Replaced `@code-reviewer` with `/code-review` throughout
-   **`agent-orchestration.md.prompt`**: Replaced `@code-reviewer` with `/code-review` in delegation triggers
-   **`README.md.prompt`**: Updated command and agent tables
-   **`environment-generator.md`**: Updated agent list and generation examples
-   **`manifest.yaml`**: Added review competencies, `/code-review` command, `code-review-workflow.md`, `/load-context` skill

### Removed

-   **`code-reviewer.md.prompt`** (agent): Replaced by `/code-review` command with parallel competency sub-agents
-   **`code-review.md.prompt`** (command): Replaced by static `/code-review` command
-   **`merge-step.md`** (command): Merge at protocol level only

---

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
