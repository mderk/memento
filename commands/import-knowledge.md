---
description: Import external knowledge into project's Memory Bank
argument-hint: <url|file|text>
---

# Import Knowledge into Memory Bank

Import external knowledge (documentation, guides, patterns, workflows) directly into the project's `.memory_bank/` directory.

## Input

The command accepts one of the following:

-   **URL**: Web page, GitHub file, Google Docs, Notion page
-   **File path**: Local file (markdown, text, etc.)
-   **Text**: Direct text in the command argument

## Process

### Phase 1: Read Source

1. **Determine source type**:

    - If starts with `http://` or `https://` → Use WebFetch to retrieve content
    - If file exists at path → Use Read tool
    - Otherwise → Treat argument as direct text content

2. **Extract content** from the source

### Phase 2: Semantic Analysis

1. **Analyze the content**:

    - Determine content characteristics:
      - Is it step-by-step instructions? → Likely **Workflow**
      - Is it "how to do X"? → Likely **Guide**
      - Is it reusable code structure? → Likely **Pattern**
      - Is it AI assistant behavior? → Likely **Agent**
      - Is it a user command? → Likely **Command**
      - Is it reusable AI capability? → Likely **Skill**
    - Extract key concepts and terminology
    - Suggest appropriate filename based on content

2. **Report analysis results** to user:
    - **Suggested type**: `[Guide/Workflow/Pattern/Agent/Command/Skill]`
    - **Suggested name**: `[suggested-name].md`
    - **Key concepts**: `[list of concepts]`
    - **Brief description**: One-sentence summary of content

### Phase 3: Find Similar Content

1. **Scan existing Memory Bank** for similar content:

    - `.memory_bank/guides/` - Development guides
    - `.memory_bank/workflows/` - Process workflows
    - `.memory_bank/patterns/` - Code patterns
    - `.claude/commands/` - Slash commands
    - `.claude/agents/` - AI agents
    - `.claude/skills/` - Agent skills

2. **Semantic comparison** using LLM:
    - Compare imported content with existing files
    - Identify files with overlapping topics or concepts
    - Report similar files found (if any)

### Phase 4: User Decision (AskUserQuestion)

1. **Determine content type based on analysis:**

    From Phase 2 semantic analysis, suggest the most appropriate type:
    - **Guide** - Implementation guides, how-to documentation
    - **Workflow** - Processes, procedures, step-by-step flows
    - **Pattern** - Code patterns, architectural patterns
    - **Agent** - AI agent definitions
    - **Command** - Slash command definitions
    - **Skill** - Reusable AI skills

2. **Ask user to confirm or choose type:**

    Use AskUserQuestion with suggested type pre-selected:

    ```
    "This appears to be a [detected type]: [brief content description]

    Where should this knowledge be added?"

    Options:
    - Guide (.memory_bank/guides/)
    - Workflow (.memory_bank/workflows/)
    - Pattern (.memory_bank/patterns/)
    - Agent (.claude/agents/)
    - Command (.claude/commands/)
    - Skill (.claude/skills/)
    ```

3. **If similar content found**, ask action:

    - Create new file (separate from existing)
    - Update existing file (merge content)

4. **Confirm filename** with user (show suggested name from Phase 2)

### Phase 5: Generate Content

1. **Format content** based on knowledge type:

    For guides:

    ```markdown
    # [Guide Title]

    ## Overview

    [Brief description]

    ## [Main Sections]

    [Content organized logically]

    ## Related

    -   [Links to related guides/patterns]
    ```

    For workflows:

    ```markdown
    # [Workflow Name]

    ## When to Use

    [Trigger conditions]

    ## Process

    ### Step 1: [Name]

    [Instructions]

    ## Completion Criteria

    [What defines success]
    ```

    For patterns:

    ```markdown
    # [Pattern Name]

    ## Problem

    [What problem this solves]

    ## Solution

    [The pattern implementation]

    ## Example

    [Code example]
    ```

    For agents (YAML frontmatter + markdown):

    ```markdown
    ---
    name: [agent-name]
    description: [Brief description]
    tools: [Bash, Read, Write, Grep, Glob]
    ---

    # [Agent Name]

    [Agent instructions]
    ```

    For commands (YAML frontmatter + markdown):

    ```markdown
    ---
    description: [Brief description]
    argument-hint: [optional arguments]
    ---

    # [Command Name]

    [Command instructions]
    ```

    For skills (directory with SKILL.md):

    ```
    .claude/skills/<skill-name>/
    ├── SKILL.md (required)
    ├── reference.md (optional)
    └── examples.md (optional)
    ```

    **SKILL.md format** (YAML frontmatter + markdown):

    ```markdown
    ---
    name: [skill-name]
    description:
        [What the skill does AND when to use it - critical for discovery]
    allowed-tools: Read, Grep, Glob # optional, restricts tool access
    ---

    # [Skill Name]

    ## Instructions

    [Step-by-step guidance for Claude]

    ## Examples

    [Concrete examples of using this skill]
    ```

    **Note**: Skills are model-invoked (Claude decides when to use them based on description), unlike commands which are user-invoked.

2. **Write the file** to appropriate directory

3. **Update index.md** (if exists) for the category

### Phase 6: Completion

1. **Report results**:

    - File created/updated: `[path]`
    - Content summary

2. **Suggest next steps**:
    - Review the generated file
    - Update cross-references if needed
    - Run `/prime` to reload context

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
/import-knowledge "When writing tests, always use descriptive names that explain what is being tested and what the expected outcome is."
```

## Notes

-   Content is written directly to Memory Bank, not as generation templates
-   Existing files can be updated or new files created based on user choice
-   The command adapts content format based on the target knowledge type
-   Use `/prime` after importing to include new knowledge in context
