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

Run tests for determined scope with coverage enabled.

See [Testing Guide](../guides/testing.md) for commands.

### Step 3: Analyze Results

| Result | Action |
|--------|--------|
| All pass | Go to Step 4 (Report) |
| Failures | Identify failing tests, analyze root cause |
| Timeout/Crash | Note infrastructure issue, retry or escalate |

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

## Coverage Gaps (if any)
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
- Coverage drops below threshold
- Environment problems

## When Used

- Ad-hoc request: "run tests", `/run-tests`
- [Development Workflow Phase 3.3](./development-workflow.md#phase-3-implementation-loop-per-unit)
- [Bug Fix Workflow](./bug-fix-workflow.md) - verify fix

## Related Documentation

- [Testing Guide](../guides/testing.md) - Commands, patterns, examples
- [Development Workflow](./development-workflow.md) - Testing during implementation
