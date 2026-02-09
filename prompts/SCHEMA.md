# Prompt File Schema

This document defines the structure and format for `.prompt` files used by the memento plugin.

## Overview

Prompt files are used by the `@environment-generator` agent to generate Memory Bank documentation, agents, and commands tailored to specific projects. Each `.prompt` file contains:

1. **YAML Frontmatter**: Metadata about the file to generate
2. **Generation Instructions**: Detailed instructions for the LLM
3. **Examples**: Sample outputs for different project types

## File Format

### YAML Frontmatter

```yaml
---
file: README.md # Output filename
target_path: .memory_bank/ # Relative path where file should be written
priority: 1 # Generation order (1=highest priority)
dependencies: [] # List of files that must be generated first
conditional: null # Condition for generation (null = always generate)
---
```

#### Frontmatter Fields

| Field          | Type           | Required | Description                                                                                         |
| -------------- | -------------- | -------- | --------------------------------------------------------------------------------------------------- |
| `file`         | string         | Yes      | Name of the output file (e.g., "README.md")                                                         |
| `target_path`  | string         | Yes      | Relative directory path where file will be written (e.g., ".memory_bank/")                          |
| `priority`     | integer        | Yes      | Generation order (1-100, lower = earlier). Files with same priority generated in alphabetical order |
| `dependencies` | array          | No       | List of files that must exist before generating this file. Empty array or null if no dependencies   |
| `conditional`  | string or null | No       | Condition expression for when to generate file. Null means always generate                          |
| `target_lines` | integer        | No       | Target line count for generated file. Used for redundancy validation in Phase 3. Omit if no target  |

#### Conditional Expressions

Conditional expressions reference fields in `project-analysis.json`:

**Simple conditionals:**

```yaml
conditional: "has_frontend"  # Generate only if frontend exists
conditional: "has_backend"   # Generate only if backend exists
conditional: "has_database"  # Generate only if database detected
```

**Negation:**

```yaml
conditional: "!has_frontend" # Generate only if NO frontend
```

**Multiple conditions (AND):**

```yaml
conditional: "has_frontend && is_monorepo"
```

**Framework-specific:**

```yaml
conditional: "backend_framework == 'Django'"
conditional: "frontend_framework == 'React'"
```

### Generation Instructions

After the frontmatter, provide detailed generation instructions for the LLM.

#### Template Variables (Optional)

You can reference reusable content blocks using `{{VARIABLE_NAME}}` syntax. Available template variables are defined in `prompts/templates/reusable-blocks.md`.

**Example usage in prompt:**

```markdown
## What is the Memory Bank?

{{MEMORY_BANK_EXPLANATION}}
```

The generator will replace `{{MEMORY_BANK_EXPLANATION}}` with the actual content from reusable-blocks.md, reducing redundancy across prompts.

**Available variables:** See `prompts/templates/reusable-blocks.md` for full list (18+ blocks covering navigation, testing, security, etc.)

#### Required Sections

1. **Context**

    - Explain what file is being generated
    - Describe its purpose in the Memory Bank system
    - Specify the audience (AI assistants, developers, etc.)

2. **Input Data**

    - Document the structure of `project-analysis.json`
    - List all available fields the LLM can use
    - Show example data structure

3. **Output Requirements**

    - Define required sections and structure
    - Specify style guidelines
    - List conditional logic rules
    - Define validation criteria

4. **Examples**

    - Provide 2-3 complete examples for different project types
    - Show how conditionals should be applied
    - Demonstrate style and tone

5. **Quality Checklist**
    - List items to verify before finalizing output
    - Include validation rules
    - Specify what to avoid

## Template Structure

````markdown
---
file: example.md
target_path: .memory_bank/
priority: 10
dependencies: []
conditional: null
target_lines: 150 # Optional: target line count for redundancy check
---

# Generation Instructions for example.md

## Context

You are generating [description] for a {{PROJECT_TYPE}} project called {{PROJECT_NAME}}.

This file serves as [purpose]. It should:

-   [Requirement 1]
-   [Requirement 2]
-   [Requirement 3]

**Tone**: [Professional/Conversational]
**Target Length**: ~150 lines (concise, no redundancy)
**Anti-redundancy**: Follow guidelines in `prompts/anti-patterns.md`

## Input Data

You have access to the following project data from `project-analysis.json`:

```json
{
  "project_name": "string",
  "project_type": "web_app|api|mobile_app|cli|library",
  "project_description": "string",

  "backend_framework": "Django|FastAPI|Express|Spring|null",
  "backend_framework_version": "string|null",
  "backend_dir": "server|backend|api|src",
  "backend_test_framework": "pytest|jest|mocha|...",

  "frontend_framework": "React|Vue|Angular|Svelte|null",
  "frontend_framework_version": "string|null",
  "frontend_dir": "client|frontend|web|src",
  "frontend_test_framework": "jest|vitest|...",

  "database": "PostgreSQL|MySQL|MongoDB|null",
  "database_version": "string|null",

  "is_monorepo": true|false,
  "primary_language": "Python|TypeScript|JavaScript|Go|Java|...",
  "package_manager": "npm|yarn|pnpm|pip|poetry|...",

  "has_database": true|false,
  "has_frontend": true|false,
  "has_backend": true|false,

  "api_style": "REST|GraphQL|gRPC|null",
  "build_tool": "Vite|Webpack|Parcel|string|null",
  "deployment_platform": "Vercel|AWS|GCP|Heroku|null",

  "dev_command": "string|null",
  "test_command": "string|null",
  "build_command": "string|null"
}
```
````

## Output Requirements

### Structure

Generate a markdown file with the following sections:

1. **Section 1**: [Description]

    - [Subsection details]
    - [Requirements]
    - Use `{{TEMPLATE_VARIABLE_NAME}}` if applicable (reduces redundancy)

2. **Section 2**: [Description]
    - [Subsection details]
    - [Requirements]

**Example using template variables:**

```markdown
## Navigation

{{NAVIGATION_TIPS}} <!-- Auto-replaced with content from reusable-blocks.md -->

## Security Checklist

{{SECURITY_CHECKLIST}} <!-- Auto-replaced with content from reusable-blocks.md -->
```

### Conditional Logic

**If `has_frontend` is true:**

```markdown
[Content to include when frontend framework detected]
```

**If `is_monorepo` is true:**

```markdown
[Content for monorepo structure]
```

**If `backend_framework` == "Django":**

```markdown
[Django-specific content]
```

### Style Guidelines

-   Professional, clear tone
-   Use proper markdown hierarchy
-   Include code blocks for commands/code
-   Use relative links for navigation
-   No placeholder text (no "TODO", "[TBD]", "Add description")
-   All content must be specific to the project
-   Grammar and spelling must be perfect

#### Anti-Redundancy Guidelines

Follow anti-patterns defined in `prompts/anti-patterns.md` (24 documented patterns):

-   **Reference, don't duplicate**: Link to Memory Bank docs instead of copying content
-   **One example per concept**: Show ONE minimal example, note alternatives in text
-   **Avoid repetitive blocks**: Don't repeat Before/After examples, checklists, or explanations
-   **Concise commands**: Don't explain obvious operations (e.g., `pip install` needs no 8-line explanation)
-   **Target reduction**: Aim for 20-30% below maximum reasonable length

**Key principle:** Agents should REFERENCE Memory Bank guides, not DUPLICATE them.

### Quality Checklist

Before finalizing, verify:

-   [ ] No `{{PLACEHOLDERS}}` remain in output (template variables were replaced)
-   [ ] All links are relative paths (.memory_bank/...)
-   [ ] Directory names match actual project structure
-   [ ] Conditional sections correctly included/excluded
-   [ ] Commands use actual project tech stack
-   [ ] Grammar and formatting perfect
-   [ ] No generic placeholder text
-   [ ] **Anti-redundancy checks** (check against `prompts/anti-patterns.md`):
    -   [ ] File length within target (if specified) or 20-30% below max
    -   [ ] No more than 1-2 code examples per concept
    -   [ ] No duplicate explanations or checklists
    -   [ ] References Memory Bank docs instead of duplicating
    -   [ ] No verbose explanations of obvious operations

## Examples

### Example 1: Django + React Monorepo

```markdown
[Complete example of expected output for this project type]
```

### Example 2: FastAPI API-only

```markdown
[Complete example of expected output for this project type]
```

### Example 3: [Another common case]

```markdown
[Complete example of expected output]
```

## Common Mistakes to Avoid

1. ❌ Leaving {{PLACEHOLDERS}} in final output
2. ❌ Using absolute paths for internal links
3. ❌ Including conditional sections that don't match project
4. ❌ Generic descriptions that could apply to any project
5. ❌ Broken or incorrect internal links
6. ❌ Inconsistent directory naming
7. ❌ Placeholder text like "TODO" or "[Add details]"
8. ❌ Poor formatting or grammar errors

````

## Project Analysis JSON Schema

The `project-analysis.json` file generated by `@project-analyzer` contains:

```json
{
  "project_name": "string",
  "project_type": "web_app|api|mobile_app|cli|library|other",
  "project_description": "string",

  "backend_framework": "string|null",
  "backend_framework_version": "string|null",
  "backend_dir": "string",
  "backend_test_framework": "string|null",

  "frontend_framework": "string|null",
  "frontend_framework_version": "string|null",
  "frontend_dir": "string|null",
  "frontend_test_framework": "string|null",

  "database": "string|null",
  "database_version": "string|null",

  "is_monorepo": true|false,
  "primary_language": "string",
  "package_manager": "string|null",

  "has_database": true|false,
  "has_frontend": true|false,
  "has_backend": true|false,

  "api_style": "REST|GraphQL|gRPC|null",
  "auth_method": "JWT|OAuth|Session|null",

  "build_tool": "string|null",
  "deployment_platform": "string|null",

  "dev_command": "string|null",
  "test_command": "string|null",
  "build_command": "string|null",

  "confidence_scores": {
    "backend_framework": 0.0-1.0,
    "frontend_framework": 0.0-1.0,
    "database": 0.0-1.0
  },

  "generation_date": "YYYY-MM-DD",
  "environment_version": "string"
}
````

## Best Practices

### Writing Effective Prompts

1. **Be Specific**: Don't say "add details", say exactly what details
2. **Provide Context**: Explain why each section exists
3. **Show Examples**: Include 2-3 complete, realistic examples
4. **Define Quality**: Explicit quality checklist with measurable criteria
5. **Handle Edge Cases**: Document what to do for unusual project structures
6. **Use Template Variables**: Reference `{{TEMPLATE_VARIABLES}}` from reusable-blocks.md for common content
7. **Follow Anti-Patterns**: Check prompt against all 24 anti-patterns in prompts/anti-patterns.md
8. **Target Conciseness**: Specify target line count if known, aim for 20-30% reduction

### Avoiding Redundancy

1. **For Agents**: Reference Memory Bank guides instead of duplicating content

    - ❌ Bad: Include 50 lines of Flask best practices inline
    - ✅ Good: "Review against [Backend Guide](../.memory_bank/guides/backend.md)"

2. **For Commands**: Reference workflows instead of duplicating steps

    - ❌ Bad: Explain entire code review process inline
    - ✅ Good: "Follow steps in [Code Review Workflow](../.memory_bank/workflows/code-review-workflow.md)"

3. **For Guides**: Use ONE minimal example per concept
    - ❌ Bad: Show 3-4 variations of pagination (offset, page, cursor)
    - ✅ Good: Show page-based pagination with note: "Alternatives: offset-based, cursor-based"

### Conditional Logic

1. **Keep It Simple**: Use simple boolean expressions
2. **Be Explicit**: Always document what each condition means
3. **Test Both Paths**: Show examples for when condition is true AND false
4. **Default Behavior**: Specify what happens if field is null/missing

### Examples

1. **Complete Examples**: Show full file output, not snippets
2. **Diverse Cases**: Cover common project types (monorepo, API-only, full-stack)
3. **Realistic Data**: Use plausible project names and descriptions
4. **Highlight Differences**: Show how output changes based on conditions

## Validation

When creating a new `.prompt` file, verify:

**Frontmatter:**

-   [ ] YAML frontmatter is valid
-   [ ] All required fields are present (`file`, `target_path`, `priority`)
-   [ ] `file` has correct extension
-   [ ] `target_path` ends with `/`
-   [ ] `priority` is 1-100
-   [ ] `conditional` expression is valid (if not null)
-   [ ] `target_lines` is reasonable (if specified)

**Instructions:**

-   [ ] Generation instructions have all 5 required sections (Context, Input Data, Output Requirements, Examples, Quality Checklist)
-   [ ] At least 2 examples provided
-   [ ] Quality checklist has 5+ items (including anti-redundancy checks)
-   [ ] No typos or grammar errors in instructions
-   [ ] Instructions are clear and unambiguous

**Optimization:**

-   [ ] Uses `{{TEMPLATE_VARIABLES}}` where appropriate (reduces duplication)
-   [ ] Follows anti-patterns from `prompts/anti-patterns.md`
-   [ ] Encourages references over duplication (especially for agents)
-   [ ] Specifies target line count or reduction percentage
-   [ ] Includes anti-redundancy guidelines in quality checklist

## File Naming

Prompt files should be named: `<output-filename>.prompt`

Examples:

-   `README.md.prompt` generates `README.md`
-   `architecture.md.prompt` generates `architecture.md`
-   `test-runner.md.prompt` generates `test-runner.md`

## Version

Schema Version: 1.3.0
Last Updated: 2025-11-18

### Changelog

**v1.3.0 (2025-11-18)**

-   Added Anti-Patterns #20-24: Workflow prompt defects
    -   #20: Workflow-Guide Confusion (workflows embed guide content)
    -   #21: Completeness Bloat (self-contained over reference-first)
    -   #22: Lost Interaction Models (critical user patterns disappear)
    -   #23: Hardcoded Tech in Prompts (Django/bcrypt in project-agnostic prompts)
    -   #24: Self-Contained Over Reference-First (document ownership confusion)
-   Fixed 7 workflow prompts (code-review, testing, agent-orchestration, create-spec, process-tasks-list, generate-tasks, create-prd)
-   Added "Reference-First Architecture" principle
-   Added "CRITICAL annotations" for interaction patterns
-   Added "Project-Agnostic Prompts" principle (use {variables})
-   Enhanced Style Guidelines with workflow vs guide separation
-   Updated Quality Checklists to validate interaction patterns
-   Documented 24 anti-patterns reference (prompts/anti-patterns.md v2.1)

**v1.2.0 (2025-11-14)**

-   Added Anti-Pattern #19: Placeholder Status Disclaimers
-   Updated all testing-related prompts to prevent "not configured yet" messages
-   Enhanced Style Guidelines with explicit anti-disclaimer instructions
-   Updated Quality Checklists to check for placeholder status messages
-   Documented 19 anti-patterns reference (prompts/anti-patterns.md)

**v1.1.0 (2025-01-14)**

-   Added `target_lines` frontmatter field for redundancy validation
-   Added Template Variables section (references to reusable-blocks.md)
-   Added Anti-Redundancy Guidelines in Style Guidelines
-   Added anti-redundancy checks to Quality Checklist
-   Added "Avoiding Redundancy" best practices with examples
-   Enhanced Validation section with optimization checks
-   Documented 18 anti-patterns reference (prompts/anti-patterns.md)
