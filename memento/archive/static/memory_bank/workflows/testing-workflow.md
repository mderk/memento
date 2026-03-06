# Rule: Run Tests

## Goal

Execute tests for specified scope, analyze results, and report findings.

## Agent Restrictions

**DO NOT modify any files.** Only run tests and report results.

- Run test commands only
- Analyze failures and suggest fixes in your response
- Return to orchestrator for actual code changes

## Process

### Step 1: Determine Scope

| Request | Scope |
|---------|-------|
| "Run tests" (no context) | Full unit test suite |
| "Run tests for [file/module]" | Specific file/module |
| "Run E2E tests" | E2E suite |
| "Run all tests" | Unit + E2E |
| During implementation | Affected modules only |

### Step 2: Execute Tests

Run tests for determined scope **with coverage enabled**.

See [Testing Guide](../guides/testing.md) for commands. Always pass the coverage flag (e.g., `--cov`, `--coverage`) so Step 3 can verify coverage.

**Coverage flags by framework:**

| Framework | Coverage flag |
|-----------|-------------|
| pytest | `--cov=<package> --cov-report=term-missing` |
| jest / vitest | `--coverage` |
| go test | `-cover -coverprofile=coverage.out` |
| rspec | (uses SimpleCov in spec_helper) |

### Step 3: Analyze Results

| Result | Action |
|--------|--------|
| All pass | Check coverage, then go to Step 4 (Report) |
| Failures | Identify failing tests, analyze root cause |
| Timeout/Crash | Note infrastructure issue, retry or escalate |

**Coverage enforcement (changed files):**

1. Identify files touched by current changes (from git diff or context)
2. Check per-file coverage in the coverage report
3. **Changed files must have 100% line coverage** — if any changed file is below 100%, write additional tests before reporting success
4. If a changed file has untested legacy code unrelated to current changes, still add tests to reach 100% — this is intentional: touching a file means owning its coverage

**Failure Diagnosis:**

1. Read test file to understand what's being tested
2. Analyze stack trace to identify failure point
3. Read source code at failure location
4. Identify root cause (logic error, missing data, environment)
5. Provide specific fix with code example

### Step 4: Report

**Format:**

```
## Summary
- Total: X tests
- Passed: Y
- Failed: Z
- Skipped: W
- Coverage: X%

## Failed Tests (if any)

### [test_name] (file:line)
- **Root Cause**: Why it failed
- **Fix**: Specific code change
- **Priority**: [CRITICAL|REQUIRED|SUGGESTION]

## Coverage (changed files)
- Files touched by current changes: X% (target: 100%)
- Missing lines: [list specific uncovered lines]
- Action: [write tests to reach 100% on changed files]

## Coverage Gaps (project-wide)
- Uncovered critical paths
- Recommended tests

## Next Steps
- Action items
```

**Severity Levels:**

| Level | Meaning | Action |
|-------|---------|--------|
| `[CRITICAL]` | Security, data loss, blocks merge | Fix immediately |
| `[REQUIRED]` | Bugs, broken functionality | Fix before PR |
| `[SUGGESTION]` | Optimization, refactoring | Consider fixing |

### Step 5: On Failure

1. Show failing test names and errors
2. Identify likely cause (recent change, flaky test, environment)
3. Suggest next step:
   - Fix code if bug found
   - Run single failing test in isolation
   - Check test environment

**Escalate to user when:**

- Flaky tests (intermittent failures)
- Performance issues (tests taking >10s)
- Coverage on changed files cannot reach 100% (e.g., code requires hardware/external service not mockable)
- Coverage drops below project-wide threshold
- Environment problems

## When Used

- Ad-hoc request: "run tests", `/run-tests`
- [Development Workflow Phase 3.3](./development-workflow.md#phase-3-implementation-loop-per-unit)
- [Bug Fixing](./bug-fixing.md) - verify fix

## Related Documentation

- [Testing Guide](../guides/testing.md) - Commands, patterns, examples
- [Development Workflow](./development-workflow.md) - Testing during implementation
