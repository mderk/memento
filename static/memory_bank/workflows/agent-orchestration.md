# Rule: Agent Delegation and Orchestration

## Goal

Guide the main AI assistant in delegating work to specialized agents with precise trigger conditions and communication protocols.

## Agent Reference

**For agent capabilities**: See [AI Agent Handbook](../guides/ai-agent-handbook.md)

**This workflow defines**: WHEN to invoke agents, HOW to communicate, and WHEN to run in parallel.

## Delegation Triggers

### @test-runner

- **When**: Implementation complete OR code changes made
- **Action**: Automatically invoke (loop until green)
- **Do NOT wait**: Tests run proactively during development, not after review

### /code-review (command)

- **When**: Tests passing AND ready for PR
- **Action**: Automatically run after tests green (spawns parallel competency sub-agents)
- **Do NOT run**: Before tests pass, during active development

### @design-reviewer (if available)

- **When**: UI changes (components, styles, layouts)
- **Action**: Automatically invoke after implementation

### @research-analyst

- **When**: User asks "How do I implement X?" or "Find documentation on Y"
- **Use for**: External APIs, library patterns, web resources

### @Explore

- **When**: ANY codebase search needed (files, patterns, structure)
- **Action**: ALWAYS use instead of direct Glob/Grep calls
- **Use for**: Finding files, searching code, understanding structure
- **CRITICAL**: Saves context by delegating search to subagent

### @Developer

- **When**: Phase 3 of [Development Workflow](./development-workflow.md)
- **Use for**: Code implementation per task unit
- **Receives**: Task description + context (files, patterns)

### @general-purpose

- **When**: Complex tasks combining multiple operations
- **Use for**: Research + code exploration

## Communication Protocol

**Before Invoking**:

1. Explain why invoking agent
2. Set expectations (what agent will check)

**During**:

3. Wait for agent to complete

**After**:

4. Summarize findings
5. Offer next steps to user

**Example**:
"Implementation complete. Running code review to ensure quality standards."
→ Runs `/code-review`
→ "Code review done: 3 findings triaged. See triage table above. Implement fixes or proceed?"

## Parallel Execution

**When to run in parallel**:

- User explicitly requests both (e.g., "review and test")
- Independent operations (not dependent on each other)

**When NOT to run in parallel**:

- Code review depends on tests passing first
- Design review might require code changes

**Safety**: Default to sequential unless user requests parallel or operations are clearly independent.

## Proactive Invocation

The AI must be **proactive**: when triggers are met, automatically invoke agents (don't wait for user to ask).

**Correct**: "Implementation complete. Running tests..." → [invokes @test-runner]

**Incorrect**: "Implementation complete." → [waits for user]

## Related Documentation

- **Agent Details**: [AI Agent Handbook](../guides/ai-agent-handbook.md)
- **Code Review Process**: [Code Review Workflow](./code-review-workflow.md)
- **Testing Process**: [Testing Workflow](./testing-workflow.md)
- **Development Process**: [Development Workflow](./development-workflow.md)
