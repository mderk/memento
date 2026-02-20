# Workflows

This directory contains step-by-step workflow documentation for common development tasks.

## What Are Workflows?

Workflows are actionable rulebooks for completing specific development tasks. Each provides:

- Step-by-step instructions
- Decision points and triggers
- Links to relevant guides

## Available Workflows

### Development

- [Development Workflow](./development-workflow.md) - Mandatory workflow for any code changes (5 phases)
- [Bug Fixing](./bug-fixing.md) - Systematic bug fix process

### Planning & Documentation

- [Create PRD](./create-prd.md) - Generate Product Requirements Document
- [Create Spec](./create-spec.md) - Generate Technical Specification from PRD

### Protocol-Based Development

- [Create Protocol](./create-protocol.md) - Generate protocol with mini-ADR and step files from PRD
- [Process Protocol](./process-protocol.md) - Execute protocol steps with quality checks
- [Git Worktree Workflow](./git-worktree-workflow.md) - Worktree setup + merge procedure for protocols

### Quality Assurance

- [Code Review Workflow](./code-review-workflow.md) - Competency-based code review process
- [Testing Workflow](./testing-workflow.md) - Testing quality gates
- [Agent Orchestration](./agent-orchestration.md) - AI agent delegation and coordination

### Maintenance

- [Update Memory Bank](./update-memory-bank.md) - Keep documentation synchronized with code
- [Doc Gardening](./doc-gardening.md) - Reduce drift, redundancy, broken links
- [Commit Message Rules](./commit-message-rules.md) - Commit formatting standards
- [Git Worktree Workflow](./git-worktree-workflow.md) - Parallel branch development

## Quick Reference

| Task | Workflow |
|------|----------|
| Any code change | [Development Workflow](./development-workflow.md) |
| Fixing a bug | [Bug Fixing](./bug-fixing.md) |
| Writing PRD | [Create PRD](./create-prd.md) |
| Writing tech spec | [Create Spec](./create-spec.md) |
| Planning implementation | [Create Protocol](./create-protocol.md) |
| Executing protocol step | [Process Protocol](./process-protocol.md) |
| Reviewing code | [Code Review Workflow](./code-review-workflow.md) |
| Running tests | [Testing Workflow](./testing-workflow.md) |
| Delegating to AI agents | [Agent Orchestration](./agent-orchestration.md) |
| Updating docs after changes | [Update Memory Bank](./update-memory-bank.md) |
| Keeping docs healthy | [Doc Gardening](./doc-gardening.md) |

## Workflow Structure

All workflows follow this format:

1. **Goal**: What this workflow accomplishes
2. **Process**: Numbered steps to execute
3. **Related Documentation**: Links to guides and other workflows

Protocol workflows add:

- **Mini-ADR format**: Context, Decision, Rationale, Consequences
- **Step files**: Separate files for each implementation phase
- **Findings**: Runtime discoveries captured during execution

## Related Documentation

- [Architecture Guide](../guides/architecture.md)
- [Backend Guide](../guides/backend.md)
- [Frontend Guide](../guides/frontend.md)
- [Testing Guide](../guides/testing.md)
- [AI Agent Handbook](../guides/ai-agent-handbook.md)
- [Code Review Guidelines](../guides/code-review-guidelines.md)
