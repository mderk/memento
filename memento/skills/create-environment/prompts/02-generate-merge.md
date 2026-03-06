# Generate Memory Bank File (Merge-Aware)

You are regenerating a Memory Bank documentation file that will be merged with existing local changes.

## Current Item

```json
{{variables.current_file}}
```

## Instructions

1. **Read the prompt template** at `{{variables.plugin_root}}/{{variables.current_file.prompt_path}}`
2. **Read the project analysis** at `.memory_bank/project-analysis.json`
3. **Read anti-patterns** at `{{variables.plugin_root}}/prompts/anti-patterns.md`
4. **Follow the prompt template instructions** to generate the target file content
5. **Write the generated content ONLY to the clean directory**: `/tmp/memento-clean/{{variables.current_file.target}}`

Do NOT write directly to `{{variables.current_file.target}}` — the merge step handles that.

## Quality Rules

### Content Generation
- Follow the generation instructions in the prompt template exactly
- Use framework-appropriate patterns based on project-analysis.json
- Commands must use values from project-analysis.json `commands` object — never hardcode package managers
- Code examples must show framework PATTERNS with generic entity names (Item, Button, Widget) — never invent project-specific models, import paths, or API endpoints

### No Placeholders
- Never use placeholder text like "TODO", "[fill in]", "[TBD]", "Add description"
- Never leave `{{TEMPLATE_VARIABLES}}` in final output — use actual values from project data

### Links and References
- ONLY link to files that WILL exist (check generation plan items)
- Never link to non-existent files
- If unsure whether a file exists, don't create the link

### Context-Only Generation
- ONLY use data from project context (project-analysis.json, prompt template, project files)
- Never invent business data, market info, metrics, or statistics

### Anti-Redundancy
- Limit code examples to 1-2 per concept
- Explain concepts once, use cross-references elsewhere
- Prefer concise over verbose
- Reference framework docs instead of explaining basic concepts

## Output

Write the clean copy only. Report what you generated.
