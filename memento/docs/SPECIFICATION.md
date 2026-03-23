# Technical Specification: Claude AI Environment Plugin

**Version**: 3.0.0
**Date**: 2026-02-20
**Relates to**: [CHANGELOG.md](../CHANGELOG.md)

## 1. Architecture Overview

### Plugin Structure

```
memento/                         # PLUGIN ROOT
├── .claude-plugin/
│   ├── plugin.json              # Plugin manifest
│   └── marketplace.json         # Marketplace metadata
├── agents/                      # Plugin's own agents
│   └── environment-generator.md # Main generation agent
├── commands/                    # Plugin commands (require plugin installed)
│   ├── create-environment.md    # Initialize AI environment
│   ├── update-environment.md    # Smart update with detection
│   ├── import-knowledge.md      # Import external knowledge
│   └── optimize-memory-bank.md  # Reduce redundancy
├── skills/                      # Plugin skills (namespaced)
│   ├── detect-tech-stack/       # Tech stack detection (Python)
│   ├── fix-broken-links/        # Link validation + repair loop
│   ├── check-redundancy/        # Redundancy analysis
│   ├── analyze-local-changes/   # Local modification detection + merge
├── prompts/                     # Generation instructions (LLM-adapted)
│   ├── SCHEMA.md               # Prompt file format spec
│   ├── anti-patterns.md        # Quality standards
│   ├── CLAUDE.md.prompt        # Root onboarding file
│   ├── memory_bank/            # Prompts for Memory Bank docs
│   │   ├── *.md.prompt         # Core docs (3 files)
│   │   ├── guides/             # Guide prompts (11 files)
│   │   ├── workflows/review/   # Review prompt (1 file)
│   │   └── patterns/           # Pattern prompts (2 files)
├── static/                      # Static content (copied as-is)
│   ├── manifest.yaml           # File list with conditionals
│   ├── commands/
│   │   └── prime.md            # /prime command
│   ├── skills/                 # Skills deployed to projects (15)
│   │   ├── code-review/
│   │   ├── develop/
│   │   ├── run-tests/
│   │   ├── commit/
│   │   ├── create-prd/
│   │   ├── create-spec/
│   │   ├── create-protocol/
│   │   ├── process-protocol/
│   │   ├── merge-protocol/
│   │   ├── update-memory-bank/
│   │   ├── doc-gardening/
│   │   ├── defer/
│   │   ├── load-context/
│   │   ├── design-reviewer/    # (conditional: has_frontend)
│   │   └── research-analyst/
│   └── workflows/              # Workflow engine definitions
│       ├── _dsl.py             # Shared DSL
│       ├── develop/            # TDD workflow
│       ├── code-review/        # Parallel competency review
│       │   └── competencies/   # Review checklists (10 files)
│       ├── testing/            # Test execution
│       ├── commit/             # Commit workflow
│       ├── create-protocol/    # Protocol creation
│       ├── process-protocol/   # Protocol execution
│       ├── merge-protocol/     # Protocol merge
│       └── verify-fix/         # Fix verification
└── docs/
    ├── SPECIFICATION.md (this file)
    ├── GETTING_STARTED.md
    ├── PROTOCOL_WORKFLOW.md
    └── CUSTOMIZATION.md

---

# What gets DEPLOYED to user's project:
user-project/
├── CLAUDE.md                    # (generated) AI assistant onboarding
├── .claude/
│   ├── commands/
│   │   └── prime.md            # (static) Load context
│   └── skills/                 # (static) All slash commands (15)
│       ├── code-review/
│       ├── develop/
│       ├── run-tests/
│       ├── commit/
│       ├── create-prd/
│       ├── create-spec/
│       ├── create-protocol/
│       ├── process-protocol/
│       ├── merge-protocol/
│       ├── update-memory-bank/
│       ├── doc-gardening/
│       ├── defer/
│       ├── load-context/
│       ├── design-reviewer/    # (if frontend)
│       └── research-analyst/
├── .workflows/                  # (static) Workflow engine definitions
│   ├── develop/                 # TDD workflow
│   ├── code-review/             # Parallel competency review
│   │   └── competencies/        # Review checklists
│   ├── testing/                 # Test execution
│   ├── commit/                  # Commit workflow
│   ├── create-protocol/         # Protocol creation
│   ├── process-protocol/        # Protocol execution
│   ├── merge-protocol/          # Protocol merge
│   └── verify-fix/              # Fix verification
└── .memory_bank/                # Agent documentation (Memory Bank)
    ├── README.md               # (generated) Navigation hub
    ├── product_brief.md        # (generated) Product vision
    ├── tech_stack.md           # (generated) Tech details
    ├── guides/                 # (generated) Implementation guides
    └── patterns/               # (generated) Code patterns
```

### Architecture Principles

**Dual Content System:**

-   **Prompt files** (`.prompt`): LLM generates project-specific content from instructions
-   **Static files**: Content copied as-is to projects (no LLM modification)
-   Both support conditional logic based on project analysis

**Prompt-Based Generation:**

-   Uses `.prompt` files containing LLM generation instructions
-   Each prompt describes how to generate a specific file
-   LLM adapts content to detected project stack
-   No placeholders - fully project-specific content

**Static Content:**

-   Files in `static/` are copied without modification
-   `manifest.yaml` defines file list and conditional expressions
-   Ideal for universal processes, checklists, reference docs
-   Evaluated against `project-analysis.json` for conditional copying

**Two-Phase Process:**

-   **Phase 1 (Planning)**: Analyze, evaluate conditionals, create plan
-   **Phase 2 (Generation)**: Copy static files, then orchestrate prompt-based generation

**Context Efficiency:**

-   Each generation agent reads only 1 prompt (~200 lines)
-   Shared context via `project-analysis.json` (~50 lines)
-   Static files require zero LLM tokens (direct copy)

## 2. Component Specifications

### 2.1 Plugin Manifest

**File**: `.claude-plugin/plugin.json`

```json
{
    "name": "memento",
    "version": "1.6.0",
    "description": "AI development environment generator with Memory Bank documentation system",
    "author": {
        "name": "Max Derkachev"
    },
    "keywords": [
        "ai",
        "documentation",
        "workflow",
        "agents",
        "code-review",
        "memory-bank"
    ]
}
```

Commands, agents, and skills are auto-discovered from standard directories (`commands/`, `agents/`, `skills/`). No path fields needed in plugin.json.

````

### 2.2 Environment Generator Agent

**File**: `agents/environment-generator.md` (plugin's agent)

```yaml
---
name: environment-generator
description: Generates complete AI development environment from prompt files
capabilities:
    - Detect project tech stack
    - Read and process .prompt files
    - Generate project-specific documentation
    - Create AI agents and slash commands
    - Handle conditional content based on stack
tools: [Bash, Glob, Grep, Read, Write, Edit]
model: sonnet
color: blue
---
````

**Behavior**:

1. **Analyze Project**: Scan for package.json, requirements.txt, go.mod, etc.
2. **Detect Stack**: Identify backend/frontend frameworks, databases, test frameworks
3. **Read Prompts**: Read all `.prompt` files from prompts/ directory
4. **Process by Priority**: Sort by priority field in YAML frontmatter
5. **Check Conditions**: Evaluate conditional expressions (e.g., "has_backend")
6. **Generate Content**: Use LLM to generate project-specific content from instructions
7. **Save Files**: Write to target_path specified in frontmatter
8. **Report Progress**: Notify user of generation progress

### 2.3 Prompt File Format

**File**: `prompts/SCHEMA.md`

Prompt files contain generation instructions for the LLM.

**Structure**:

````yaml
---
file: output-filename.md
target_path: .memory_bank/guides/
priority: 10
dependencies: ["file1.md", "file2.md"]
conditional: "has_backend"
---

# Generation Instructions for guides/output-filename.md

## Context
[What this file is for]

## Input Data
```json
{
  "project_name": "string",
  "has_backend": true|false,
  "backend_framework": "Django|FastAPI|..."
}
````

## Output Requirements

[Detailed instructions for content generation]

## Conditional Logic

[How to handle different project types]

````

**Key Fields**:
- `file`: Output filename
- `target_path`: Where to save in user's project
- `priority`: Generation order (lower = earlier)
- `dependencies`: Files that must exist first
- `conditional`: Natural language expression for when to generate

**Prompt-Generated Files**:

| Category | Examples |
|----------|----------|
| Core Docs | CLAUDE.md, README.md, product_brief.md, tech_stack.md |
| Guides | architecture.md, backend.md, frontend.md, testing.md, getting-started.md, visual-design.md |
| Review | testing.md (conditional, project-specific) |
| Patterns | index.md, api-design.md |

**Static Files** (from manifest.yaml):

| Category | Examples |
|----------|----------|
| Workflows | development-workflow.md, bug-fixing.md, code-review-workflow.md, create-protocol.md, process-protocol.md, etc. |
| Review Competencies | architecture.md, security.md, performance.md + conditional: typescript.md, python.md |
| Commands | code-review.md, develop.md, prime.md, run-tests.md, create-prd.md, create-protocol.md, etc. |
| Agents | test-runner.md, developer.md, design-reviewer.md (conditional: has_frontend), research-analyst.md |
| Skills | commit, defer (+ script), load-context (+ script) |

Exact file count depends on conditionals. See `static/manifest.yaml` for the authoritative list.

### 2.4 Main Command: /create-environment

**File**: `commands/create-environment.md`

```markdown
---
description: Initialize AI development environment with Memory Bank
argument-hint: [--auto]
---

# Create AI Environment

This command sets up a comprehensive AI development environment in your project.

## What it does

**Phase 1: Planning**
1. **Analyzes your project** - Detects technology stack automatically
2. **Scans prompt templates** - Finds all generation files (reads metadata only)
3. **Evaluates conditions** - Determines which files to generate for your stack
4. **Creates generation plan** - Shows what will be generated, waits for confirmation

**Phase 2: Generation** (after user confirms "Go")
1. **Orchestrates generation** - Launches one agent per file (prevents context overflow)
2. **Generates Memory Bank** - Creates comprehensive documentation structure
3. **Deploys agents and skills** - Copies static agents (test-runner, developer, design-reviewer, research-analyst) and skills (commit, defer, load-context)
4. **Configures commands** - Copies all static commands (code-review, develop, prime, run-tests, create-prd, create-spec, create-protocol, process-protocol, merge-protocol, update-memory-bank)

## Usage

```bash
# Two-phase process with confirmation
/create-environment
# ... review generation-plan.md ...
Go  # User confirms to proceed
````

## Workflow

### Phase 1: Create Generation Plan

**Step 1: Launch Planning Agent**

Command launches a planning agent via Task tool to:

1. Analyze project structure
2. Detect technology stack
3. Scan all .prompt files (read only frontmatter)
4. Evaluate conditionals
5. Create generation plan

**Step 2: Save Project Analysis**

Agent creates `.memory_bank/project-analysis.json`:

```json
{
  "project_name": "string",
  "project_type": "web_app|api|...",
  "has_backend": true|false,
  "has_frontend": true|false,
  "backend_framework": "Django|FastAPI|...",
  "frontend_framework": "React|Vue|...",
  "is_monorepo": true|false,
  "backend_dir": "string",
  "frontend_dir": "string|null",
  ...
}
```

**Step 3: Create Generation Plan**

Agent creates `.memory_bank/generation-plan.md`:

```markdown
# AI Environment Generation Plan

## Project Analysis

-   Project Name: MyProject
-   Backend: Django 5.2
-   Frontend: React 19
-   Is Monorepo: true

## Files to Generate via Prompts (18 files)

**Note**: Additionally, static files are copied from `static/` directory (workflows, review checklists, agents, commands, skills). See `static/manifest.yaml` for the full list.

### Priority 1-10: Core Documentation (5 files)

-   [ ] **CLAUDE.md** → `root/`
    -   Prompt: `prompts/memory_bank/CLAUDE.md.prompt`
-   [ ] **README.md** → `.memory_bank/`
    -   Prompt: `prompts/memory_bank/README.md.prompt`
        [...]

## Skipped Files (3 files)

-   ~~mobile.md~~ - has_mobile=false
```

**Step 4: User Confirms**

Present plan to user and wait for "Go" confirmation.

### Phase 2: Orchestrated Generation

**Step 5: Generate Files One-by-One**

Command orchestrates generation by launching one agent per file:

```
For each file in generation-plan.md (in priority order):
  1. Check dependencies
  2. Launch agent via Task tool with:
     - Prompt file path
     - Project analysis path
     - Target output path
  3. Agent reads:
     - One .prompt file (~200 lines)
     - project-analysis.json (~50 lines)
  4. Agent generates file
  5. Command marks file as [x] in plan
  6. Report progress: "✓ Generated filename (5/18)" for prompts, "📋 Copied filename (static)" for static files
  7. Continue to next file
```

**Key Advantage:** Each agent has minimal context (~250 lines) instead of all prompts at once, preventing context overflow.

**Step 6: Report Results**

```
✅ AI Environment created successfully!

Deployed:
  - .memory_bank/  (agent documentation)
  - .claude/skills/  (15 skills)
  - .claude/commands/  (1 command)
  - .workflows/  (8 workflow definitions + review competencies)
  - CLAUDE.md  (onboarding guide)

Next steps:
  1. Review generated docs in .memory_bank/README.md
  2. Customize product_brief.md with your product vision
  3. Try: /prime to load context
  4. Try: /code-review <files> to review code

Total files deployed: ~60
```

## Error Handling

**Phase 1 Failures (Planning):**

-   If project detection fails, report error and suggest manual config
-   If .prompt files not found, verify plugin installation
-   If frontmatter parsing fails, report which prompt file has invalid YAML

**Phase 2 Failures (Generation):**

-   If single file generation fails:
    -   Report which file failed
    -   Show generation-plan.md to see progress
    -   User can fix issue and resume from that file
-   If dependencies missing:
    -   Report missing dependency
    -   Skip file, continue with others
-   Each agent failure is isolated (doesn't affect other files)

**File Conflicts:**

-   If .memory_bank already exists:
    -   Warn user before Phase 2
    -   Allow user to cancel or continue (overwrites existing)
    -   Consider backing up existing files first

**Recovery:**

-   generation-plan.md shows [x] for completed files
-   User can resume by running Phase 2 again
-   Already completed files can be skipped (check [x] marks)

## Examples

See [GETTING_STARTED.md](GETTING_STARTED.md) for detailed examples.

````

## 3. Prompt-Based Generation System

### 3.1 How It Works

Instead of templates with placeholders, we use **generation prompts** that instruct the LLM to create project-specific content.

**Generation Process:**
1. Agent reads `.prompt` file with generation instructions
2. Agent reads `project-analysis.json` with project data
3. Agent generates content following instructions
4. Content is fully adapted to project (no placeholders remain)

**Example prompt file structure:**
```yaml
---
file: tech_stack.md
target_path: .memory_bank/
priority: 4
dependencies: []
conditional: null
---

# Generation Instructions for tech_stack.md

## Context
You are generating the tech stack documentation for {project_name}.

## Input Data
You have access to project-analysis.json with fields:
- backend_framework, frontend_framework, database, etc.

## Output Requirements
Generate markdown with:
- Backend section (if has_backend)
- Frontend section (if has_frontend)
- Database section (if has_database)
- Adapt all examples to actual stack

## Example
[Full example for Django + React project]
````

### 3.2 Project Context Injection

**No placeholder replacement** - LLM generates project-specific content directly.

**Available data** (from project-analysis.json):

-   `project_name`, `project_type`, `project_description`
-   `has_backend`, `has_frontend`, `has_database`, `has_tests`
-   `backend_framework`, `frontend_framework`, `database`
-   `is_monorepo`, `backend_dir`, `frontend_dir`
-   `backend_test_framework`, `frontend_test_framework`
-   `package_managers` - detected package managers (`python`: uv/poetry/pip, `node`: yarn/pnpm/npm)
-   `commands` - generated run commands (`test_backend`, `test_frontend`, `e2e`, `install_backend`, `install_frontend`, `dev_backend`, `dev_frontend`)

**LLM adapts:**

-   Examples to match actual frameworks
-   Directory names to match actual structure
-   Commands use detected package runners (e.g., `uv run pytest` instead of `pytest`)
-   Conditionally includes/excludes sections

### 3.3 Prompt Files Organization

**Prompt files** (LLM-generated per project):

-   `prompts/CLAUDE.md.prompt` - Root onboarding
-   `prompts/memory_bank/*.prompt` - Core docs (README, product_brief, tech_stack)
-   `prompts/memory_bank/guides/*.prompt` - Implementation guides
-   `prompts/memory_bank/workflows/review/*.prompt` - Testing competency (conditional)
-   `prompts/memory_bank/patterns/*.prompt` - Design patterns

**Static entries** (copied without LLM modification, from `static/manifest.yaml`):

-   `static/memory_bank/workflows/` - Workflow documentation
-   `static/memory_bank/workflows/review/` - Review competency checklists
-   `static/agents/` - test-runner, developer, design-reviewer, research-analyst
-   `static/commands/` - Slash commands
-   `static/skills/` - commit, defer, load-context

Exact counts depend on conditionals. See `static/manifest.yaml` for the authoritative list.

**Each prompt file contains:**

-   YAML frontmatter (metadata)
-   Generation instructions (context, requirements, examples)
-   Quality checklist
-   Common mistakes to avoid

See `prompts/SCHEMA.md` for full specification.

## 4. Data Flow

### Phase 1: Planning

```
User runs /create-environment
         ↓
Command launches planning agent via Task
         ↓
Agent analyzes project (detect frameworks)
         ↓
Agent creates .memory_bank/project-analysis.json
         ↓
Agent scans all .prompt files (reads frontmatter only)
         ↓
Agent evaluates conditionals per project
         ↓
Agent creates .memory_bank/generation-plan.md
         ↓
Command presents plan to user
         ↓
User reviews plan
         ↓
User confirms with "Go"
```

### Phase 2: Orchestrated Generation

```
Command reads generation-plan.md
         ↓
For each file in plan (sorted by priority):
  │
  ├─→ Command checks dependencies
  │
  ├─→ Command launches agent via Task
  │       Agent reads ONE .prompt file
  │       Agent reads project-analysis.json
  │       Agent generates content
  │       Agent writes to target_path
  │
  ├─→ Command marks file [x] in plan
  │
  └─→ Command reports progress (N/18)
         ↓
All files generated
         ↓
Command reports final summary
```

**Key characteristics:**

-   Minimal context per agent (~250 lines vs ~7500)
-   Isolated agent failures (one file doesn't break others)
-   Transparent progress tracking (generation-plan.md)
-   Resumable (can continue from [x] marks)
-   Two-commit system (Generation Base + Generation Commit) preserves clean plugin base for 3-way merge across repeated updates

## 5. Performance Characteristics

**Phase 1 (Planning):**

-   Project analysis (detect-tech-stack): ~5-10 seconds
-   Scanning 18 .prompt frontmatters + manifest: ~2-3 seconds
-   Creating plan: ~1 second
-   **Total Phase 1**: ~10-15 seconds

**Phase 2 (Generation):**

-   Static file copy: 40 files × instant = ~0 seconds
-   Per-file generation: ~5-10 seconds each
-   Prompt files × ~7 seconds each
-   Progress visible throughout (updates after each file)
-   **Total Phase 2**: ~3-4 minutes

**Context usage per agent:**

-   Planning agent: ~2000 lines (frontmatters + detection logic)
-   Generation agents: ~250 lines each (1 prompt + project-analysis.json)
-   **No context overflow risk**

**Scalability:**

-   Adding new prompt files: Linear cost (1 agent per file)
-   Adding static files: Zero LLM cost (direct copy)
-   Each agent isolated (parallel execution possible in future)

## 6. Edge Cases

**Empty project directory:**

-   Planning agent reports: "Cannot detect technology stack"
-   User can manually create project-analysis.json

**Existing Memory Bank:**

-   Phase 2 warns before overwriting
-   User can backup or cancel
-   Resumable if interrupted (check [x] marks in plan)

**No config files detected:**

-   Planning agent uses defaults
-   User reviews plan before Phase 2
-   Can manually edit project-analysis.json

**Mixed tech stacks:**

-   Planning agent detects all frameworks
-   Conditional logic includes relevant sections
-   Example: Django + React generates both backend and frontend guides

**Non-standard structure:**

-   Planning agent does best-effort detection
-   User can edit project-analysis.json before Phase 2
-   Generated files may need manual adjustment

## 7. Error Recovery

**Phase 1 failures:**

-   Planning agent fails → No files generated
-   Safe to retry (no side effects)

**Phase 2 failures:**

-   Single file fails → Other files continue
-   generation-plan.md shows progress ([x] marks)
-   Can resume from last successful file
-   Each agent isolated (no cascading failures)

**Interruption handling:**

-   User cancels → generation-plan.md preserved
-   Can resume by running Phase 2 again
-   Already generated files marked [x]
-   Command can skip completed files

## 8. Implemented Enhancements (since v1.0.0)

-   `/update-environment` command with smart detection of tech stack changes and plugin updates (v1.0.1)
-   `/update-memory-bank` command and findings system for protocol workflows (v1.1.0)
-   `/develop` skill for TDD development workflow (v1.0.3)
-   Competency-based `/code-review` with parallel review (v1.2.0)
-   Hub-and-spoke testing documentation (testing.md + testing-backend.md + testing-frontend.md) (v1.3.0)
-   Package manager detection and command generation (v1.3.0)
-   Backlog system (`/defer` skill) for deferred work tracking (v1.3.0)
-   Git-based 3-way merge with two-commit system (Base/Commit) for preserving local changes across repeated updates (v1.4.0)
-   `analyze-local-changes` skill: detect modifications, section-level merge, commit-generation, update-plan with source hash tracking (v1.4.0)
-   `/doc-gardening` command and workflow for Memory Bank maintenance (v1.5.0)
-   `/update-memory-bank <protocol>` for post-protocol Memory Bank updates (v1.5.0)
-   `AGENTS.md` wrapper, namespaced gardening commands, absolute skill script paths (v1.5.0)

## 9. Future Enhancements

-   Parallel execution for Phase 2 (reduce generation time)
-   Custom prompt directories (user-defined generation templates)
-   Team prompt sharing (shared .prompt repositories)
-   Incremental regeneration (only changed files)

---

**Implementation Status**: Active development
**Last Updated**: 2026-02-20
**Version**: 3.0.0
