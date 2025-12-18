# Code Review Checklist

Universal checklist for conducting effective code reviews.

## Before Reviewing

- [ ] Understand the context: read the PR description and linked issues
- [ ] Check the scope: ensure changes match the stated purpose
- [ ] Review in manageable chunks (< 400 lines ideally)

## Code Quality

### Correctness
- [ ] Logic is correct and handles edge cases
- [ ] No obvious bugs or regressions
- [ ] Error handling is appropriate

### Readability
- [ ] Code is self-documenting with clear naming
- [ ] Complex logic has explanatory comments
- [ ] Consistent formatting and style

### Maintainability
- [ ] No code duplication (DRY principle)
- [ ] Functions/methods have single responsibility
- [ ] Dependencies are appropriate and minimal

## Security

- [ ] No hardcoded secrets or credentials
- [ ] Input validation for user-provided data
- [ ] No SQL injection, XSS, or command injection vulnerabilities
- [ ] Sensitive data is properly handled

## Testing

- [ ] New code has appropriate test coverage
- [ ] Tests are meaningful (not just for coverage)
- [ ] Edge cases are tested
- [ ] Existing tests still pass

## Performance

- [ ] No obvious performance issues (N+1 queries, etc.)
- [ ] Resource usage is reasonable
- [ ] Caching is used where appropriate

## Documentation

- [ ] Public APIs are documented
- [ ] Breaking changes are noted
- [ ] README updated if needed

## Feedback Guidelines

### Do
- Be specific and constructive
- Explain the "why" behind suggestions
- Acknowledge good solutions
- Ask questions instead of demanding changes

### Don't
- Be nitpicky about style (use linters)
- Make it personal
- Block on minor issues
- Approve without actually reviewing

## After Review

- [ ] All comments addressed or discussed
- [ ] CI/CD checks pass
- [ ] Approval given with confidence
