# TypeScript Review

## Scope

Type safety, TypeScript idioms, async patterns, module design. Applies in addition to universal review competencies.

## Rules

### Type Safety

- No `any` without a comment justifying why. Use `unknown` + narrowing instead.
- No type assertions (`as X`) to silence errors — fix the underlying type mismatch
- Strict null checks: handle `null`/`undefined` explicitly, don't use `!` (non-null assertion) unless provably safe
- Union types over optional fields when variants have different shapes (discriminated unions)
- Generics: use when type relationship matters, not for everything (`T extends string` — what's the point?)

### Inference & Declarations

- Let TypeScript infer where obvious: `const x = 5` not `const x: number = 5`
- Annotate function signatures (params and return types) — callers rely on these
- Avoid return type inference for public/exported functions — explicit return type catches unintended changes
- Use `satisfies` for compile-time validation without widening: `config satisfies Config`

### Patterns

- Prefer `interface` for object shapes, `type` for unions/intersections/utilities
- Enums: prefer `as const` objects over `enum` (better tree-shaking, no runtime artifact)
- Avoid class inheritance for code reuse — prefer composition (functions, mixins)
- Barrel exports (`index.ts`): only at package boundaries, not within internal modules (slows bundling, creates circular dependencies)

### Async

- Every `Promise` has error handling (`.catch()` or try/catch with `await`)
- Independent async operations run in parallel: `Promise.all`, not sequential `await`
- Async functions that don't use `await` — should they be async? (unnecessary microtask)
- AbortController for cancellable operations (fetch, long tasks)
- No floating promises (promise created but not awaited or stored)

### Null Handling

- Optional chaining (`?.`) over nested `if (x && x.y && x.y.z)`
- Nullish coalescing (`??`) over logical OR (`||`) for defaults (avoids false/0/"" gotchas)
- Differentiate between "absent" (`undefined`) and "explicitly nothing" (`null`) — pick one convention and stick to it

### Modules

- Named exports over default exports (better refactoring, auto-import)
- Circular imports: restructure, don't patch with lazy imports
- Side effects in module scope: explicit and necessary, not accidental

## Anti-Patterns

| Anti-Pattern | Example | Fix |
|---|---|---|
| Any escape hatch | `(data as any).field` | Type the data properly or use `unknown` |
| Enum runtime cost | `enum Status { ... }` | `const Status = { ... } as const` |
| Non-null lie | `element!.click()` | Guard: `if (element) element.click()` |
| Stringly typed | `type: string` for known set | `type: 'active' \| 'inactive'` |
| Over-generic | `function wrap<T>(x: T): T` | Just use the concrete type |

## Severity

- **[CRITICAL]**: `any` in security-sensitive code, unhandled promise rejection in production path
- **[REQUIRED]**: Untyped external data, missing null checks, floating promises
- **[SUGGESTION]**: Better inference usage, `satisfies`, named exports
