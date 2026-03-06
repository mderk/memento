# Generate Memory Bank File

You are generating a Memory Bank documentation file for a software project.

## Current Item

```json
{{variables.item}}
```

## Instructions

1. **Read the prompt template** at `{{variables.plugin_root}}/{{variables.item.prompt_path}}`
2. **Read the project analysis** at `.memory_bank/project-analysis.json`
3. **Read anti-patterns** at `{{variables.plugin_root}}/prompts/anti-patterns.md`
4. **Follow the prompt template instructions** to generate the target file content
5. **Write the generated content** to `{{variables.item.target}}`
6. **Also write a clean copy** to `/tmp/memento-clean/{{variables.item.target}}`

## Quality Rules

### Content Generation
- Follow the generation instructions in the prompt template exactly
- Use framework-appropriate patterns based on project-analysis.json
- Commands must use values from project-analysis.json `commands` object — never hardcode package managers
- Code examples must show framework PATTERNS with generic entity names (Item, Button, Widget) — never invent project-specific models, import paths, or API endpoints

### No Placeholders
- Never use placeholder text like "TODO", "[fill in]", "[TBD]", "Add description"
- Never leave `{{TEMPLATE_VARIABLES}}` in final output — use actual values from project data
- All content must be specific to the project, not generic

### Links and References
- ONLY link to files that WILL exist (check generation plan items)
- Never link to non-existent files — this is treated as hallucination
- Never use placeholder links like `[Text](TBD)` — either link to a real file or use plain text
- If unsure whether a file exists, don't create the link

### Context-Only Generation
- ONLY use data from project context (project-analysis.json, prompt template, project files)
- Never invent business data, market info, metrics, dates, or statistics
- When context lacks data, note what's needed rather than hallucinating

### Anti-Redundancy
- Limit code examples to 1-2 per concept
- Explain concepts once, use cross-references elsewhere
- Prefer concise over verbose — aim for 20-30% below prompt's target max lines
- Reference framework docs instead of explaining basic concepts
- Skip obvious explanations

## Output

Write both files. Report what you generated.
