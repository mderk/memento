# Classify Task

You are classifying a development task to determine scope, type, complexity, and relevant Memory Bank sections.

## Task

{{variables.task}}

## Instructions

1. Read the task description carefully
2. Determine the scope (backend / frontend / fullstack) by analyzing what systems are affected
3. Determine the type (bug / feature / refactor / documentation)
4. Determine the complexity:
   - **trivial**: 1-3 lines, single file, no logic changes (typos, formatting, simple renames)
   - **simple**: one file, clear implementation
   - **complex**: multiple files, dependencies between changes
5. Decide if this qualifies for **fast track** (all of: trivial, single file, no logic change, location known)
6. Read the Memory Bank README at `.memory_bank/README.md` to identify relevant guides
7. Based on task scope, read the **relevant sections** (not the whole file):

| Task scope | Read |
|---|---|
| Backend | `.memory_bank/guides/backend.md` |
| Frontend | `.memory_bank/guides/frontend.md` |
| Fullstack | Both backend + frontend guides |
| API work | `.memory_bank/patterns/api-design.md` (if exists) |

8. State what you found: which patterns apply, what conventions to follow, any relevant examples from the guides

Before classifying, consider: What systems are affected? What Memory Bank sections are relevant? Are there applicable patterns from the guides you read?

## Output

Respond with a JSON object matching the output schema with your classification and the list of guides you consulted.
