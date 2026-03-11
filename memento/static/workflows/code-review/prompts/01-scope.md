# Determine Review Scope

Identify changed files and select appropriate review competencies.

## Scope

{{variables.scope}}

If a scope value was provided above, use it as the git diff argument (e.g., `git diff --name-only <scope>`).
If no scope was provided (empty or blank), use uncommitted + staged changes: run `git diff --name-only` and `git diff --cached --name-only`.

If a `workdir` variable is set, run all git commands inside that directory (e.g., `git -C {{variables.workdir}} diff --name-only`). Otherwise use the current working directory.

## Instructions

1. Get the list of changed files using the scope above
2. List available competency checklists: `ls .memory_bank/workflows/review/`
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

5. Always include **simplicity**. Only include competencies that have a matching `.md` file in `review/`.

## Output

Respond with a JSON object matching the output schema with the file list and selected competencies.
