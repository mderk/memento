# Architecture Review

## Scope

Structural integrity of changes: dependencies, boundaries, abstractions, patterns.

Review this AFTER understanding the project's architecture from `.memory_bank/guides/architecture.md`.

## Rules

### Dependencies

- No circular dependencies between modules/packages
- Dependencies flow inward: handlers → services → domain → data
- No skipping layers (handler calling data layer directly)
- New dependencies justified — prefer existing libraries over adding new ones

### Boundaries

- Each module/package has a clear public API
- Internal implementation details not leaked through exports
- Cross-boundary communication through defined interfaces, not direct access
- Database models don't leak into API responses (use DTOs/serializers)

### Abstractions

- Each abstraction earns its existence (used in 2+ places or hides genuine complexity)
- No leaky abstractions — callers don't need to know internals
- Abstraction level consistent within a function/class (don't mix high-level orchestration with low-level details)
- No premature abstraction — concrete first, abstract when pattern emerges

### Patterns

- New code follows patterns established in the codebase
- If deviating from a pattern, the reason is clear and documented
- No mixing competing patterns for the same concern (e.g., two state management approaches)
- Patterns applied consistently — no half-implementations

### API Design

- API contracts stable — breaking changes versioned or migrated
- Naming consistent with existing APIs
- Error responses follow project conventions
- Pagination, filtering, sorting patterns reused (not reinvented)

## Anti-Patterns

| Anti-Pattern | Signal | Why It Matters |
|---|---|---|
| God object | Class/module with 10+ responsibilities | Impossible to test, reason about, or modify safely |
| Feature envy | Code heavily accessing another module's data | Belongs in the other module |
| Shotgun surgery | One change requires edits in 5+ unrelated files | Missing abstraction or wrong boundaries |
| Inappropriate intimacy | Module depends on another's internal structure | Fragile coupling, breaks on refactor |
| Speculative generality | Abstract factory for one implementation | Complexity without value |

## Severity

- **[CRITICAL]**: Circular dependency, layer violation, breaking API contract
- **[REQUIRED]**: Wrong abstraction level, leaky abstraction, pattern inconsistency
- **[SUGGESTION]**: Naming improvement, minor boundary refinement
