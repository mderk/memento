# Rule: Code Review Process

## Goal

Review code changes through specialized competency checks — each focused on a specific quality dimension.

## Review Competencies

Each competency is a standalone checklist. Apply competencies relevant to the change.

### Universal (always applicable)

| Competency     | File                                                   | When to prioritize                               |
| -------------- | ------------------------------------------------------ | ------------------------------------------------ |
| Architecture   | [review/architecture.md](./review/architecture.md)     | New modules, dependency changes, API changes     |
| Security       | [review/security.md](./review/security.md)             | Auth, input handling, external data, secrets     |
| Performance    | [review/performance.md](./review/performance.md)       | Queries, loops, caching, large data paths        |
| Data Integrity | [review/data-integrity.md](./review/data-integrity.md) | Migrations, transactions, constraints, deletions |
| Simplicity     | [review/simplicity.md](./review/simplicity.md)         | All changes (final pass)                         |

### Project-specific (when generated)

| Competency | File                                           | Conditional                |
| ---------- | ---------------------------------------------- | -------------------------- |
| Testing    | [review/testing.md](./review/testing.md)       | Test files changed         |

### Language-specific (when present)

| Competency | File                                           | Conditional                |
| ---------- | ---------------------------------------------- | -------------------------- |
| TypeScript | [review/typescript.md](./review/typescript.md) | `.ts`/`.tsx` files changed |
| Python     | [review/python.md](./review/python.md)         | `.py` files changed        |

### Competency selection

Not every review needs all competencies. Select based on what changed:

-   **Schema/migration files** → data-integrity + performance
-   **API endpoints/handlers** → security + architecture
-   **New module/package** → architecture + simplicity
-   **Business logic** → simplicity + language-specific
-   **Test files** → testing (if testing competency exists)
-   **Config/infra only** → security (secrets check), skip others

## Agent Restrictions

**DO NOT modify any files.** Only review and report findings.

-   Read code and analyze against competency rules
-   Report issues with severity levels in your response
-   Do not fix code — return to orchestrator for changes
-   Do not create report files — output directly in response

## Process

### Scenario A: Informal Iteration Review

1. **Request Review**: Developer asks to review uncommitted changes
2. **Select Competencies**: Determine relevant competencies from change type
3. **Review**: Apply each competency's rules against changed files
4. **Report**: Post findings with severity tags per [Code Review Guidelines](../guides/code-review-guidelines.md#severity-levels)
5. **Iterate**: Developer fixes, re-review if needed

### Scenario B: Formal Pull Request Review

**Stage 1: Author Pre-Review**

1. Run CI locally (lint, tests, build)
2. Self-review against [Code Review Guidelines](../guides/code-review-guidelines.md)
3. Create PR with clear description

**Stage 2: Review** 4. **Competency reviews**: Run `/code-review` — spawns parallel sub-agents per competency 5. **Human review**: Assess business logic, context, trade-offs

**Stage 3: Merge** 6. Address feedback from all reviewers 7. Merge when approved and CI green

## Output Format

Each competency review produces:

```
## [Competency Name] Review

**Verdict**: PASS | ISSUES FOUND

### Findings

[CRITICAL] file:line — description
  Why: explanation
  Fix: suggestion

[REQUIRED] file:line — description
  Why: explanation
  Fix: suggestion

[SUGGESTION] file:line — description
```

Orchestrator synthesizes into a single report with overall recommendation:

-   **APPROVE**: No critical/required issues
-   **APPROVE WITH COMMENTS**: Suggestions only
-   **REQUEST CHANGES**: Critical or required issues found

## Finding Triage

Every CRITICAL or REQUIRED finding must receive an explicit verdict — never batch-dismiss.

| Verdict | When to use | Action |
|---------|-------------|--------|
| **FIX** | Finding is in the current diff or directly caused by it | Fix before commit, re-review |
| **DEFER** | Finding is pre-existing, not introduced by this change | Create issue or add to tech debt tracker, document in step findings |
| **ACCEPT** | Finding is a conscious design decision | Document rationale in step findings or code comment |

### Rules

- **Pre-existing issues still matter.** If a reviewer flags a pre-existing REQUIRED issue, it gets DEFER — not silence. Track it.
- **No batch dismissal.** "All findings are pre-existing, skipping" is not valid. Each finding gets its own line in the triage table.
- **Triage table is part of the review output.** The orchestrator includes it when synthesizing results.

### Triage table format

```markdown
| # | Finding | Verdict | Rationale |
|---|---------|---------|-----------|
| S1 | shell=True in run_multi_step_scanner | DEFER | Pre-existing (step 2), tracked in #123 |
| S2 | Missing input validation on output_dir | FIX | Introduced in this diff |
| C1 | File exceeds 300 lines | ACCEPT | Converter adds 55 lines to 860-line file, split planned for step 07 |
```

## Related Documentation

-   [Code Review Guidelines](../guides/code-review-guidelines.md) — Project-specific standards and feedback process
-   [Architecture Guide](../guides/architecture.md)
-   [Testing Workflow](./testing-workflow.md)
