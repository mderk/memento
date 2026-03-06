# Generate Memory Bank File

You are generating a Memory Bank documentation file for a software project.

## Current Item

```json
{{variables.item}}
```

## Instructions

1. **Read the prompt template** at `{{variables.plugin_root}}/{{variables.item.prompt_path}}`
2. **Read the project analysis** at `.memory_bank/project-analysis.json`
3. **Follow the prompt template instructions** to generate the target file content
4. **Write the generated content** to `{{variables.item.target}}`
5. **Also write a clean copy** to `/tmp/memento-clean/{{variables.item.target}}`

## Rules

- Follow the generation instructions in the prompt template exactly
- Use framework-appropriate patterns based on project-analysis.json
- Never use placeholder text like "TODO" or "[fill in]"
- Use generic example names (Item, Button, Widget), never project-specific models
- Commands must use the project's actual tools (from project-analysis.json)

## Output

Write both files. Report what you generated.
