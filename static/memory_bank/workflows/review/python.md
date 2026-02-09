# Python Review

## Scope

Type annotations, Pythonic idioms, async patterns, module structure. Applies in addition to universal review competencies.

## Rules

### Type Annotations

- All function signatures annotated (parameters + return type)
- Use modern syntax (Python 3.10+): `str | None` not `Optional[str]`, `list[str]` not `List[str]`
- `Any` requires justification comment — use `object` or proper generics instead
- Dataclasses or Pydantic for structured data, not plain dicts
- TypedDict for dict shapes that must stay dicts (JSON responses, configs)

### Pythonic Patterns

- Comprehensions over `map`/`filter` with lambdas: `[x.name for x in items if x.active]`
- Context managers for resource management: `with open(f) as fh:` not manual open/close
- f-strings for formatting (not `%` or `.format()`)
- `pathlib.Path` over `os.path` for file operations
- `enumerate()` over manual index tracking
- Unpacking: `a, b = pair` not `a = pair[0]; b = pair[1]`

### Error Handling

- Catch specific exceptions, never bare `except:` or `except Exception:`
- Don't use exceptions for flow control — check conditions first
- Custom exceptions for domain errors, inheriting from appropriate stdlib base
- Context in error messages: what failed, with what input, expected what

### Async

- `async`/`await` used consistently — no mixing sync and async in the same flow without explicit bridging
- Blocking calls (file I/O, subprocess, sync HTTP) not called from async context without `run_in_executor`
- Independent coroutines gathered: `asyncio.gather()` or `TaskGroup`, not sequential `await`
- Cancellation handled: `asyncio.CancelledError` not silently swallowed

### Module Structure

- One module, one responsibility. If a module has two unrelated classes, split.
- `__init__.py`: public API only, no logic. Avoid `from module import *`
- Circular imports: restructure modules, don't use deferred imports as a band-aid
- Constants at module level, in UPPER_SNAKE_CASE

### Testing Patterns

- Hard to test = wrong structure. Extract the logic, inject the dependencies.
- `pytest` fixtures over `setUp`/`tearDown`
- Parametrize repetitive test cases: `@pytest.mark.parametrize`
- Mock at boundaries (external APIs, databases), not internal functions

## Anti-Patterns

| Anti-Pattern | Example | Fix |
|---|---|---|
| Mutable default | `def f(items=[])` | `def f(items=None)` then `items = items or []` |
| Broad except | `except Exception: pass` | Catch specific, handle or re-raise |
| God module | 500-line `utils.py` | Split by domain: `string_utils.py`, `date_utils.py` |
| Dict overuse | Passing `dict` with 8 keys everywhere | Dataclass or Pydantic model |
| Import side effects | Module-level DB connection or HTTP call | Lazy initialization or explicit `init()` |

## Severity

- **[CRITICAL]**: Bare except hiding errors, mutable default with mutation, async blocking call
- **[REQUIRED]**: Missing type annotations on public API, broad exception handling, dict-as-struct
- **[SUGGESTION]**: Modern syntax upgrades, comprehension opportunities, pathlib usage
