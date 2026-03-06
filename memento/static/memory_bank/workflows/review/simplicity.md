# Simplicity Review

## Scope

Unnecessary complexity, dead code, over-engineering, readability. This is the final pass — everything else has been checked, now ask: "Is this as simple as it can be?"

## Rules

### YAGNI

- No code for hypothetical future requirements (configurable when one config exists, generic when one case exists)
- No feature flags for things that could just be the code
- No backward-compatibility shims for internal APIs — just change the callers
- If a function parameter is always the same value, inline it

### Abstractions

- Every abstraction used in 2+ places OR hides genuine complexity
- No wrapper that just delegates to one other function
- No interface/protocol/abstract class with a single implementation (unless at a system boundary)
- Helper/utility classes: if used once, inline; if used in one module, keep local

### Dead Code

- No commented-out code — it's in git history
- No unused imports, variables, functions, or classes
- No unreachable branches (always-true/false conditions)
- No TODO/FIXME without an issue reference

### Readability

- Functions do one thing. If you need "and" to describe it, split it.
- Nesting depth <= 3 levels. Use early returns, guard clauses, extraction.
- Boolean expressions: extract to named variable if not obvious (`isEligible` vs `age > 18 && status !== 'banned' && !deleted`)
- Prefer explicit over clever. A readable 5-line version beats a cryptic 1-liner.
- Self-documenting names: no abbreviations unless universally understood (id, url, http — OK; usr, mgr, ctx — not OK)

### Duplication vs Abstraction

- 2 occurrences: tolerate duplication
- 3+ occurrences: consider extraction, but only if the duplicated code changes for the same reason
- Don't unify code that's similar today but changes for different reasons (coincidental duplication)
- Simple duplicated code is better than a complex shared abstraction

### Size

- Functions: ideally < 30 lines. If longer, look for extraction opportunities
- Files: if > 300 lines, consider splitting by responsibility
- Parameters: > 4 parameters suggests the function does too much or needs a config object
- PRs: > 400 lines changed — can it be split?

## Anti-Patterns

| Anti-Pattern | Signal | Fix |
|---|---|---|
| Speculative generality | Factory for one product, strategy for one algorithm | Inline, extract later if needed |
| Gold plating | Extra features nobody asked for | Remove |
| Primitive obsession | Passing 5 related params instead of an object | Group into struct/dataclass/type |
| Deep nesting | 4+ levels of if/for/try | Guard clauses, extract function |
| Clever code | Bitwise tricks, regex golf, chained ternaries | Explicit version with clear names |

## Severity

- **[CRITICAL]**: (rare for simplicity) Complexity that obscures a bug
- **[REQUIRED]**: Dead code in production path, abstraction with single use adding indirection, unreachable branches
- **[SUGGESTION]**: Naming improvements, nesting reduction, extraction opportunity
