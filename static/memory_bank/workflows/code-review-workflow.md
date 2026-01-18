# Rule: Code Review Process

## Goal

To guide AI assistants and developers in reviewing code through two scenarios: informal iteration reviews for rapid feedback and formal pull request reviews for merge-ready code.

## Agent Restrictions

**DO NOT modify any files.** Only review and report findings.

- Read code and analyze against guidelines
- Report issues with severity levels in your response
- Do not fix code — return to orchestrator for changes
- Do not create report files — output directly in response

## Output

- **Informal Review**: Direct feedback in chat
- **Formal Review**: GitHub/GitLab PR comments
- **Reference**: [Code Review Guidelines](../guides/code-review-guidelines.md) for detailed checklists

## Process

### Scenario A: Informal Iteration Review

1. **Request Review**: Developer asks AI to review uncommitted files
2. **AI Analyzes**: Review files against [Code Review Guidelines](../guides/code-review-guidelines.md)
3. **Provide Feedback**: Post findings with severity tags
   - Severity definitions: [Severity Levels](../guides/code-review-guidelines.md#severity-levels)
   - How to respond: [Responding to Feedback](../guides/code-review-guidelines.md#responding-to-review-feedback)
4. **Developer Iterates**: Fix issues before committing

### Scenario B: Formal Pull Request Review

**Stage 1: Author Pre-Review**
1. **Run CI Locally**: Ensure linting, tests, builds pass
2. **Self-Review**: Check code against [Code Review Guidelines](../guides/code-review-guidelines.md)
3. **Create PR**: Write clear description (purpose, changes, testing)

**Stage 2: Review**
4. **AI Review**: Code reviewer agent posts findings as PR comments
5. **Human Review**: Reviewers assess architecture, business logic, context

**Stage 3: Merge**
6. **Address Feedback**: Fix issues from AI and human reviewers
7. **Merge PR**: Merge when approved and CI green
8. **Post-Merge**: Update docs, create tickets for technical debt

## Related Documentation

- [Code Review Guidelines](../guides/code-review-guidelines.md) - Detailed checklists and protocols
- [Architecture Guide](../guides/architecture.md)
- [Backend Guide](../guides/backend.md)
- [Frontend Guide](../guides/frontend.md)
- [Testing Workflow](./testing-workflow.md)
