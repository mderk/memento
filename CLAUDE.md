# Claude Assistant Onboarding Guide

## 🚀 Project Overview

**Memento** is a Claude Code plugin that automatically generates AI-friendly development environments for any project. It creates comprehensive documentation (Memory Bank), specialized AI agents, slash commands, and workflow automation.

**This is a META-PROJECT**: It generates Memory Bank documentation systems for OTHER projects, not for itself.

### What Memento Does

1. **Analyzes any codebase** - Detects tech stack (frameworks, databases, languages)
2. **Generates Memory Bank** - Creates `.memory_bank/` with guides, workflows, and patterns
3. **Deploys AI agents** - Code reviewer, test runner, design reviewer, research analyst
4. **Provides commands** - `/prime`, `/code-review`, `/create-prd`, `/create-spec`, etc.
5. **Adapts to projects** - Uses conditional logic to generate relevant content only

### Technology Stack

- **Core**: Claude Code Plugin System
- **Templates**: Markdown with YAML frontmatter
- **Scripting**: Python (validation tools)
- **Generation**: Two-phase LLM-based approach
- **Version Control**: Git

## 🏗️ Architecture

### Two-Phase Generation System

**Phase 1: Planning**
- Scans project (package.json, requirements.txt, etc.)
- Detects frameworks, libraries, project structure
- Creates `project-analysis.json` with detected values
- Generates `generation-plan.md` with file list and priorities

**Phase 2: Generation**
- **Static files**: Universal workflows copied as-is from `static/`
- **Prompt-based**: One LLM generation per file using templates from `prompts/`
- Substitutes project-specific values (no placeholders)
- Validates links and checks redundancy

### Directory Structure

```
memento/
├── .claude-plugin/          # Plugin configuration
│   ├── plugin.json          # Plugin manifest
│   ├── marketplace.json     # Marketplace metadata
│   └── skills/              # Reusable skills
│       ├── fix-broken-links/
│       └── check-redundancy/
├── prompts/                 # Generation templates
│   ├── memory_bank/         # Docs: guides, workflows, patterns
│   ├── agents/              # AI agent definitions
│   ├── commands/            # Slash command definitions
│   ├── anti-patterns.md     # Quality standards
│   └── SCHEMA.md            # Template format spec
├── static/                  # Universal content (copied as-is)
│   └── memory_bank/
│       ├── workflows/       # Development, protocol workflows
│       └── guides/          # Code review checklist
├── commands/                # Slash command implementations
│   ├── create-environment.md
│   ├── import-knowledge.md
│   ├── optimize-memory-bank.md
│   └── fix-broken-links.md
├── agents/                  # Agent source definitions
│   └── environment-generator.md
├── scripts/                 # Validation utilities
│   ├── validate-links.py
│   ├── check-redundancy.py
│   └── README.md
├── docs/                    # Plugin documentation
│   ├── SPECIFICATION.md     # Complete technical spec
│   ├── GETTING_STARTED.md   # User guide
│   └── CUSTOMIZATION.md     # Customization guide
├── README.md                # Plugin overview
└── CHANGELOG.md             # Version history
```

### Key Components

**1. Prompt Templates** (`prompts/`)
- `.prompt` files with YAML frontmatter
- Contain generation instructions, not content
- LLM adapts content to each project's tech stack
- Example: `prompts/memory_bank/tech_stack.md.prompt`

**2. Static Files** (`static/`)
- Universal content copied without modification
- Manifest-based with conditional logic
- Example: `static/memory_bank/workflows/development-workflow.md`

**3. Skills** (`.claude-plugin/skills/`)
- **detect-tech-stack**: Analyzes project to detect frameworks, databases, test frameworks, libraries
- **fix-broken-links**: Validates and fixes Memory Bank links
- **check-redundancy**: Analyzes documentation for verbosity

**4. Commands** (`commands/`)
- `/create-environment`: Generate complete Memory Bank
- `/update-environment`: Smart update with tech stack detection
- `/import-knowledge`: Add external knowledge to prompts
- `/optimize-memory-bank`: Reduce redundancy
- `/fix-broken-links`: Validate and repair links

**5. Agents** (`prompts/agents/`)
- **test-runner**: Test execution, comprehensive reporting
- **design-reviewer**: UI/UX compliance (conditional)
- **research-analyst**: Information gathering from web/docs

**6. Commands** (`static/commands/`)
- **`/code-review`**: Parallel competency-based code review (architecture, security, performance, data-integrity, simplicity, testing)

## 🔧 Development Workflow

### Adding New Prompt Templates

1. Create `.prompt` file in appropriate directory:
   - `prompts/memory_bank/guides/` for guides
   - `prompts/memory_bank/workflows/` for workflows
   - `prompts/agents/` for agents
   - `prompts/commands/` for commands

2. Add YAML frontmatter:
   ```yaml
   ---
   file: output-name.md
   target_path: .memory_bank/guides/
   priority: 15
   dependencies: []
   conditional: null  # or "has_backend", "frontend_framework == 'React'", etc.
   ---
   ```

3. Write generation instructions (NOT final content):
   - Context: What is being generated
   - Input data: Project analysis values
   - Output requirements: Structure and format
   - Quality checklist: Standards to meet

4. Follow anti-patterns from `prompts/anti-patterns.md`

5. Test with `/create-environment` on sample project

### Adding Static Files

1. Create file in `static/memory_bank/[type]/`
2. Add entry to `static/manifest.yaml`:
   ```yaml
   - source: memory_bank/workflows/my-workflow.md
     target: .memory_bank/workflows/my-workflow.md
     conditional: null  # or conditional expression
   ```

3. Test generation to verify copying

### Validation Standards

**Link Validation**:
```bash
python scripts/validate-links.py
```
- Checks all internal markdown links
- Validates file existence
- Reports broken references

**Redundancy Check**:
```bash
python scripts/check-redundancy.py <file>
```
- Analyzes repeated phrases
- Threshold: 10% redundancy
- Flags verbose content

## 📋 Prompt Engineering Guidelines

### Template Structure

```yaml
---
file: example.md
target_path: .memory_bank/guides/
priority: 20
conditional: null
---

# Generation Instructions for guides/example.md

## Context
[What is being generated and why]

## Input Data
```json
{
  "project_name": "string",
  "backend_framework": "string|null",
  ...
}
```

## Output Requirements
[Structure, format, sections required]

## Quality Checklist
- [ ] No placeholders remain
- [ ] Project-specific examples
- [ ] Follows anti-patterns.md
- [ ] Links are valid

## Common Mistakes to Avoid
❌ Don't: [anti-pattern]
✅ Do: [correct approach]
```

### Conditional Logic

Templates can use conditional expressions:
- `null` - Always generate (universal)
- `"has_backend"` - Only if backend detected
- `"frontend_framework == 'React'"` - Only for React
- `"has_backend && has_tests"` - Multiple conditions

### Anti-Patterns to Avoid

See `prompts/anti-patterns.md` for complete list:
- ❌ Template repetition (showing same structure 3+ times)
- ❌ Excessive examples (8+ variations)
- ❌ Hardcoded technology names
- ❌ Placeholder text in generated output
- ❌ Redundant explanations (>10% redundancy)
- ✅ Reference-first architecture
- ✅ Single source of truth
- ✅ Concise, actionable content

## 🤖 AI Agents

Agents are defined in `prompts/agents/*.prompt` and deployed to generated projects.

### Available Agents

**`/code-review` command** (static)
- Parallel competency-based review (architecture, security, performance, data-integrity, simplicity, testing)
- Auto-detects language-specific competencies (typescript, python)
- Spawns Task sub-agents per competency, synthesizes results

**test-runner** (Priority 52)
- Test execution
- Coverage reporting
- Failure analysis

**research-analyst** (Priority 53)
- Information gathering from web/docs
- Multi-source synthesis
- Implementation context

**design-reviewer** (Priority 54, conditional: has_frontend)
- UI/UX compliance
- Design system validation
- Accessibility checks

### Agent Format

```yaml
---
name: agent-name
description: When to use with concrete examples
tools: [Read, Write, Bash, WebFetch, ...]
model: sonnet
color: purple
---

[Agent behavior and instructions]
```

## 💡 Key Concepts

### Meta-Project Nature

Memento generates Memory Banks for OTHER projects:
- It doesn't use its own Memory Bank for development
- Templates define HOW to generate, not WHAT to generate
- Testing requires sample projects, not self-application

### Project-Agnostic Generation

Templates work for ANY tech stack:
- Variable substitution: `{project_name}`, `{backend_framework}`
- Conditional sections: "If has_backend: include API guide"
- Generic instructions that LLM adapts per-project

### Quality Standards

- **No placeholders**: All `{{VARIABLES}}` must be replaced
- **Low redundancy**: <10% repeated content
- **Valid links**: All markdown references must exist
- **Tech-specific**: Examples match detected frameworks
- **Actionable**: Concrete steps, not abstract concepts

## 📚 Documentation

### For Plugin Users

- `README.md` - Installation and quick start
- `docs/GETTING_STARTED.md` - Complete user guide
- `docs/CUSTOMIZATION.md` - How to customize output
- `CHANGELOG.md` - Version history

### For Plugin Developers

- `docs/SPECIFICATION.md` - Technical architecture
- `prompts/SCHEMA.md` - Template format specification
- `prompts/anti-patterns.md` - Quality standards
- `scripts/README.md` - Validation tool docs

## 🧪 Testing

### Manual Testing

1. Create sample project with known stack (e.g., Flask + React)
2. Run `/create-environment`
3. Verify generated files match project
4. Check for placeholders, broken links
5. Validate conditional logic worked

### Validation Scripts

```bash
# Link validation (run after generation)
python scripts/validate-links.py

# Redundancy check (sample files)
python scripts/check-redundancy.py .memory_bank/README.md
```

### Test Projects

Maintain reference projects for testing:
- Flask API (Python backend only)
- Next.js (React + API routes)
- Go CLI (no frontend/backend)

## 🔄 Common Tasks

### Update Prompt Template

1. Edit template in `prompts/[type]/[name].md.prompt`
2. Test generation on sample project
3. Run validation scripts
4. Update priority if dependencies changed

### Add New Conditional

1. Add detection logic to project analyzer
2. Update `project-analysis.json` format
3. Use in template: `conditional: "has_feature"`
4. Test with projects that have/lack feature

### Fix Generated Content Quality

1. Identify issue (placeholder, redundancy, broken link)
2. Update prompt template instructions
3. Add to quality checklist in template
4. Add to anti-patterns.md if general issue
5. Regenerate and validate

## 📖 Quick Reference

### File Priorities

- 1-40: Memory Bank documentation
- 50-59: Agent definitions
- 60-69: Command definitions

### Common Conditionals

- `null` - Always include
- `has_backend` - Backend framework detected
- `has_frontend` - Frontend framework detected
- `has_database` - Database detected
- `has_tests` - Test framework detected
- `backend_framework == 'Django'` - Specific framework

### Essential Commands

```bash
# Generate environment
/create-environment

# Import external knowledge
/import-knowledge <url|file|text>

# Validate links
/fix-broken-links

# Load context
/prime
```

---

**Important**: This is a plugin development project. Focus on template quality, not on using the plugin on itself. Test with external projects to verify generation works correctly.

For complete technical details, see `docs/SPECIFICATION.md`.
