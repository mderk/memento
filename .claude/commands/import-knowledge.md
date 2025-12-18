---
description: Import external knowledge into the plugin as .prompt or static files
argument-hint: <url|file|text>
---

# Import Knowledge into Plugin

Import external knowledge (documentation, guides, patterns) into the Memento plugin.

**Two destination types:**
- **Prompt files** (`.prompt`) → Content is adapted by LLM for each project
- **Static files** → Content is copied as-is to projects (with conditional logic)

## Input

The command accepts one of the following:
- **URL**: Web page, GitHub file, Google Docs, Notion page
- **File path**: Local file (markdown, text, etc.)
- **Text**: Direct text in the command argument

## Process

### Phase 1: Read Source

1. **Determine source type**:
   - If starts with `http://` or `https://` → Use WebFetch to retrieve content
   - If file exists at path → Use Read tool
   - Otherwise → Treat argument as direct text content

2. **Extract content** from the source

### Phase 2: Semantic Analysis

1. **Analyze the content**:
   - Determine topic category (backend, frontend, testing, workflow, pattern, agent, command, skill)
   - Extract key concepts and terminology
   - Suggest appropriate filename based on content
   - **Detect technology specificity** for conditional suggestion:
     - Universal content (code review, git workflow) → `conditional: null`
     - Language-specific (Ruby guide) → `conditional: "backend_language == 'Ruby'"`
     - Framework-specific (React patterns) → `conditional: "frontend_framework == 'React'"`
     - Feature-specific (CI/CD workflow) → `conditional: "has_ci"`

2. **Report analysis results** to user:
   - Topic: `[detected topic]`
   - Suggested name: `[suggested-name].md`
   - Key concepts: `[list of concepts]`
   - **Suggested conditional**: `[expression or "null (universal)"]`

### Phase 3: Find Similar Content

1. **Scan existing content** for similar topics:

   **Prompt files:**
   - `prompts/memory_bank/guides/` - Development guides
   - `prompts/memory_bank/workflows/` - Process workflows
   - `prompts/memory_bank/patterns/` - Code patterns
   - `prompts/commands/` - Slash commands
   - `prompts/agents/` - AI agents
   - `prompts/skills/` - Agent skills

   **Static files:**
   - `static/memory_bank/guides/` - Static guides
   - `static/memory_bank/workflows/` - Static workflows
   - `static/memory_bank/patterns/` - Static patterns

2. **Semantic comparison** using LLM:
   - Compare imported content with existing files (both .prompt and static)
   - Identify files with overlapping topics or concepts
   - Report similar files found (if any)

### Phase 4: User Decision (AskUserQuestion)

1. **Ask destination type**:

   Present analysis and ask:
   ```
   "This is [topic description].
   Suggested conditional: [expression]

   How should this content be added to projects?"

   A) Generate with prompt (LLM adapts content to each project)
   B) Copy as static file (content copied without changes)
   ```

   **Guidance for recommendation:**
   - Recommend **prompt** if content references specific implementations, APIs, or code examples that vary by project
   - Recommend **static** if content is a universal process, checklist, or reference that applies to all projects unchanged

2. **Ask knowledge type** (if not obvious from analysis):

   **If prompt chosen:**
   - Guide → `prompts/memory_bank/guides/<name>.md.prompt`
   - Workflow → `prompts/memory_bank/workflows/<name>.md.prompt`
   - Pattern → `prompts/memory_bank/patterns/<name>.md.prompt`
   - Agent → `prompts/agents/<name>.md.prompt`
   - Command → `prompts/commands/<name>.md.prompt`
   - Skill → `prompts/skills/<skill-name>/SKILL.md.prompt`

   **If static chosen:**
   - Guide → `static/memory_bank/guides/<name>.md`
   - Workflow → `static/memory_bank/workflows/<name>.md`
   - Pattern → `static/memory_bank/patterns/<name>.md`

3. **If static chosen**, confirm conditional:
   ```
   "Suggested conditional: [expression]

   A) Accept suggested conditional
   B) Always add (no condition)
   C) Custom condition (specify)"
   ```

4. **If similar content found**, ask action:
   - Create new file (separate from existing)
   - Update existing file (merge content)

5. **Confirm filename** with user

### Phase 5A: Generate .prompt File (if prompt destination chosen)

1. **Create YAML frontmatter** based on knowledge type:

   For guides/workflows/patterns:
   ```yaml
   ---
   file: <name>.md
   target_path: .memory_bank/guides/  # or workflows/, patterns/
   priority: 50
   dependencies: []
   conditional: null
   ---
   ```

   For commands:
   ```yaml
   ---
   file: <name>.md
   target_path: .claude/commands/
   priority: 55
   dependencies: []
   conditional: null
   ---
   ```

   For agents:
   ```yaml
   ---
   file: <name>.md
   target_path: .claude/agents/
   priority: 60
   dependencies: []
   conditional: null
   ---
   ```

   For skills:
   ```yaml
   ---
   file: SKILL.md
   target_path: .claude/skills/<skill-name>/
   priority: 65
   dependencies: []
   conditional: null
   ---
   ```

   **Skill generation instructions should produce**:
   ```markdown
   ---
   name: [skill-name]
   description: [What the skill does AND when to use it - critical for discovery]
   allowed-tools: Read, Grep, Glob  # optional
   ---

   # [Skill Name]

   ## Instructions
   [Step-by-step guidance]

   ## Examples
   [Concrete examples]
   ```

   **Note**: Skills are model-invoked (Claude decides when to use based on description).

2. **Generate prompt content**:
   - Write generation instructions based on imported knowledge
   - Include context section explaining the purpose
   - Add input data requirements (if applicable)
   - Define output structure and requirements
   - Add quality checklist
   - List common mistakes to avoid

3. **Write the file** to appropriate directory in `prompts/`

### Phase 5B: Create Static File (if static destination chosen)

1. **Write the content file**:
   - Copy/write content to `static/memory_bank/[type]/<name>.md`
   - Preserve original formatting (no LLM modification)
   - Ensure proper markdown structure

2. **Update manifest.yaml**:
   - Read existing `static/manifest.yaml`
   - Add new entry to the `files` array:
     ```yaml
     - source: memory_bank/[type]/<name>.md
       target: .memory_bank/[type]/<name>.md
       conditional: [confirmed conditional or null]
     ```
   - Write updated manifest

3. **Verify entry**:
   - Confirm file exists at source path
   - Confirm manifest entry is valid YAML

### Phase 6: Completion

1. **Report results**:

   **If prompt file created:**
   - File created: `prompts/[type]/[name].md.prompt`
   - Target in projects: `[target_path]/[name].md`
   - Note: "Content will be adapted by LLM for each project"

   **If static file created:**
   - File created: `static/memory_bank/[type]/[name].md`
   - Manifest updated: `static/manifest.yaml`
   - Conditional: `[expression or "always copied"]`
   - Target in projects: `.memory_bank/[type]/[name].md`
   - Note: "Content will be copied without changes"

2. **Suggest next steps**:

   **For prompt files:**
   - Review generated .prompt file
   - Test generation with `/create-environment`
   - Update index.md.prompt if needed

   **For static files:**
   - Review static file content
   - Verify conditional expression is correct
   - Test with `/create-environment` on a matching project

## Examples

### Import from URL
```
/import-knowledge https://docs.example.com/api-design-guide
```

### Import from local file
```
/import-knowledge ./docs/my-workflow.md
```

### Import from GitHub
```
/import-knowledge https://github.com/org/repo/blob/main/CONTRIBUTING.md
```

### Import direct text
```
/import-knowledge "When writing tests, always use descriptive names..."
```

## Notes

- **Prompt files** (`.prompt`): LLM generates project-specific content from instructions
- **Static files**: Content copied as-is to projects (no LLM modification)
- Use conditional expressions to control when static files are copied
- Static files are ideal for universal processes, checklists, and reference docs
- Prompt files are better when content needs adaptation to project tech stack
- Use `/create-environment` to test both prompt and static files in a target project
