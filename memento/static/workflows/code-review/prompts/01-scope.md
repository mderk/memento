# Determine Review Scope

Identify changed files and select appropriate review competencies.

## Scope

Resolved: {{variables.resolved_scope}}
Raw: {{variables.scope}}

If a resolved scope is available (non-empty), use it as the git diff argument: `git diff --name-only <scope>`.
Otherwise, determine scope from the raw value: if it's a git ref or range, use it with `git diff`; if empty, use uncommitted + staged changes (`git diff --name-only` and `git diff --cached --name-only`).

When constructing a git diff from a raw scope, always use three-dot notation (`A...B`). Three-dot diffs show only changes since the merge-base, preventing phantom removals from a stale branch. Convert two-dot (`A..B`) to three-dot; for a bare ref like `origin/dev`, use `origin/dev...HEAD`.

If a `workdir` variable is set, run all git commands inside that directory (e.g., `git -C {{variables.workdir}} diff --name-only`).

## Instructions

1. Get the list of changed files using the scope above.
2. List available competency checklists: `ls .workflows/code-review/competencies/`
3. Select competencies based on changed files using auto-detection:

| File pattern | Competencies |
|---|---|
| `*.py` | architecture, security, performance, simplicity, **python** |
| `*.ts`, `*.tsx` | architecture, security, performance, simplicity, **typescript** |
| `*migration*`, `*schema*`, `*.sql` | **data-integrity**, performance |
| `*auth*`, `*login*`, `*token*`, `*secret*` | **security**, architecture |
| `*test*`, `*spec*` | **testing** |
| `.protocols/`, PRDs, specs | **protocol-completeness** |
| Any other code | architecture, simplicity |
| Config/docs only | security (secrets scan only) |

4. Refine selection using these heuristics:
   - **Schema/migration files** → data-integrity + performance
   - **API endpoints/handlers** → security + architecture
   - **New module/package** → architecture + simplicity
   - **Business logic** → simplicity + language-specific
   - **Bug fixes / test files** → testing + simplicity
   - **Config/infra only** → security (secrets check), skip others

5. Always include **simplicity**. Only include competencies that have a matching `.md` file in `competencies/`.

## Output

Respond with a JSON object matching the output schema with the file list and selected competencies.
