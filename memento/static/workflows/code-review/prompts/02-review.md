# Review: {{variables.item}} Competency

Review the code changes against the **{{variables.item}}** competency rules.

## Changed Files

{{results.scope}}

## Working Directory

{{variables.workdir}}

If a working directory is shown above, prepend it to file paths when reading changed files.

## Competency Rules: {{variables.item}}

{{variables.competency_rules}}

## Instructions

1. Read each changed file listed in the scope (prepend workdir if set)
2. Apply the competency rules above against the changes
4. For each finding, determine severity:
   - **CRITICAL**: Security vulnerability, data loss risk, blocks merge
   - **REQUIRED**: Bug, broken functionality, must fix before merge
   - **SUGGESTION**: Optimization, style improvement, nice-to-have
5. Provide specific fix suggestions for each finding
6. If you spot a pre-existing issue in unchanged code that is CRITICAL or REQUIRED, flag it with `pre_existing: true`. Only flag pre-existing issues that are directly adjacent to or affected by the current changes.

## Output

Respond with a JSON object matching the output schema. Set `competency` to "{{variables.item}}" on each finding.

## Constraints

- Do NOT modify any files
- Only read and analyze code
