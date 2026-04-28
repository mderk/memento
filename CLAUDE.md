# Claude Assistant Onboarding Guide

## Start Here

**Read `.memory_bank/README.md`** - the single source of truth for this project.

It contains:

- Project overview and navigation
- **MANDATORY development workflow** (required before any coding)
- Guides, patterns, and workflows
- AI agent delegation rules

All technical documentation lives in the Memory Bank. This file only points you there.

## Agent behavior

- Be concise by default.
- Prefer action over explanation.
- If asked for a plan, give the plan immediately.
- If asked to do something, do it immediately unless blocked.
- Do not promise a future answer when you can give it now.
- Do not repeat context unless needed.
- Keep responses dense and short; avoid long preambles and summaries.
- If blocked, state the blocker briefly and ask one clear question.
- After acting, report only: what changed, result, blockers.

## Documentation-First Rule

**Before using Glob, Grep, or exploring code** for any task, follow this order:

1. **Read this file** (CLAUDE.md)
2. **Read `.memory_bank/README.md`** - find the relevant guide in the navigation table
3. **Read the specific guide**
4. **Only then** search or explore code if needed

The README.md contains navigation tables that point directly to documentation.
Do not search before reading the README.md.
