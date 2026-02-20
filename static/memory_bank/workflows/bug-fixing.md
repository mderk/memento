# Rule: Bug Fix Process

## Goal

Systematic process for identifying, fixing, and preventing bugs.

## Severity Levels

| Severity | Description                                 | Response       |
| -------- | ------------------------------------------- | -------------- |
| Critical | System down, data loss, security breach     | Immediate      |
| High     | Major feature broken, many users affected   | Within 4 hours |
| Medium   | Feature partially broken, workaround exists | Within 2 days  |
| Low      | Minor issue, cosmetic problem               | Next sprint    |

## Process

### Phase 1: Reproduce

1. Read bug report — note steps to reproduce, expected vs actual behavior
2. Create branch: `git checkout -b fix/descriptive-name`
3. Reproduce locally following exact steps
4. Document reproduction steps

### Phase 2: Diagnose Root Cause

1. Add targeted logging around suspected area
2. Use debugger — set breakpoints, step through, inspect variables
3. Check recent changes: `git log --oneline --follow path/to/file`
4. Identify root cause — ask: Why did this happen? What assumption was wrong? What edge case wasn't handled?

**Common root causes**: Missing null check, incorrect error handling, race condition, off-by-one error, type mismatch, missing validation.

### Phase 3: Write Failing Test

1. Write a test that triggers the exact bug — test expected behavior, not current behavior
2. Run the test — confirm it **fails** before proceeding
3. Cover edge cases if applicable (empty inputs, boundary values, concurrent access)

See [Testing Guide](../guides/testing.md) for framework-specific patterns.

### Phase 4: Implement Fix

1. Make **minimal** fix — only what's broken
2. Verify test now passes
3. Run full test suite — no regressions introduced

### Phase 5: Review and Merge

1. Run full test suite
2. Self-review against checklist below
3. Create PR with: Bug description, Root cause, Fix, Testing done
4. Get review, address feedback, merge

## Self-Review Checklist

-   [ ] Bug is fixed and no longer reproduces
-   [ ] Regression test added
-   [ ] Edge cases handled
-   [ ] No new bugs introduced
-   [ ] Full test suite passes
-   [ ] Commit message references issue number

## Hotfix Procedure (Critical Bugs)

For production-breaking issues:

```bash
git checkout main && git pull
git checkout -b hotfix/critical-bug-name
# Fix (minimal changes only) → test → commit
git push origin hotfix/critical-bug-name
# Create PR → quick review → merge → deploy
```

**Hotfix rules**: Minimal changes only, test added, quick review, deploy immediately, schedule post-mortem.

## Common Bug Patterns

| Pattern        | Example                       | Fix                      |
| -------------- | ----------------------------- | ------------------------ |
| Null/undefined | `user.name` when user is None | Check before access      |
| Off-by-one     | `range(len(items) + 1)`       | Verify bounds            |
| Race condition | Check-then-act without lock   | Use atomic operations    |
| Type mismatch  | `"1" + "2" = "12"`            | Explicit type conversion |

## Best Practices

**DO**: Reproduce before fixing, write failing test first, make minimal changes, check edge cases, verify in production

**DON'T**: Fix without reproducing, skip tests, make large refactors during bug fix, assume fix works without testing

## Related Documentation

-   [Development Workflow](./development-workflow.md)
-   [Testing Workflow](./testing-workflow.md)
-   [Code Review Workflow](./code-review-workflow.md)
-   [Testing Guide](../guides/testing.md)
