# Analyze Changes and Compose Commit Message

You are composing git commit messages for staged changes.

## Git State

{{variables.git_state}}

## Diff File

The full diff is at: `{{variables.diff_info.diff_path}}` ({{variables.diff_info.diff_lines}} lines)

## User Instructions

{{variables.user_args}}

## Instructions

If context_files are attached to this action, read them first — they contain externalized data (git state, etc.).

1. Read the commit message rules at `.memory_bank/workflows/commit-message-rules.md`
2. Read the diff file at `{{variables.diff_info.diff_path}}`
3. Analyze the changes:
   - Identify the main theme(s) of the changes
   - Decide if this is a single cohesive commit or should be split
4. **When to split**: only split if the user explicitly asked (e.g., "split by themes") OR changes clearly cover 2+ completely independent themes (different features, unrelated bug fixes)
5. For each group, compose:
   - `files`: list of files belonging to this group (every file in the diff must appear in exactly one group)
   - `subject`: commit message subject line following the rules (prefix, imperative, <72 chars, focus on "why")
   - `body`: optional body (only if subject alone isn't enough — rare)

**Default to a single group** unless there's a clear reason to split.

## Output

Respond with a JSON object matching the CommitPlan schema:

```json
{
  "groups": [
    {
      "files": ["src/foo.py", "src/bar.py"],
      "subject": "feat: add rate limiting to auth endpoints",
      "body": null
    }
  ]
}
```
