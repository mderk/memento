# Rule: Update Memory Bank

## Goal

Keep Memory Bank documentation synchronized with code changes.

## When to Use

- After completing features (code review passed)
- After architectural changes
- After adding/removing dependencies
- After changing established patterns
- After protocol completion (collect Memory Bank Impact items)

## Process

### Step 1: Identify What Changed

Review your changes and categorize:

| Change Type | Examples |
|-------------|----------|
| API changes | New endpoints, modified responses, deprecated routes |
| Component patterns | New component structures, state management changes |
| Dependencies | Added/removed packages, version upgrades |
| Architecture | New services, changed data flow, infrastructure |
| Patterns | New coding patterns, conventions, best practices |

### Step 2: Map Changes to Memory Bank Files

| Change Type | Target Files |
|-------------|--------------|
| API routes, backend logic | `guides/backend.md`, `patterns/api-design.md` |
| Frontend components | `guides/frontend.md`, `guides/visual-design.md` |
| Dependencies, stack | `tech_stack.md` |
| Architecture decisions | `guides/architecture.md` |
| Testing patterns | `guides/testing.md` |
| New workflows | `workflows/` directory |
| New patterns | `patterns/` directory |

### Step 3: Update Affected Files

For each identified file:

1. Read current content
2. Identify section to update
3. Make minimal, focused changes
4. Preserve existing structure and style

**Update principles:**
- Add new information, don't remove unless obsolete
- Keep examples current and working
- Update version numbers if dependencies changed
- Add cross-references to related docs

### Step 4: Validate Links

Run link validation to ensure no broken references:

```bash
/memento:fix-broken-links
```

Or manually check:
- Internal links `[text](./path)` resolve correctly
- Code references match actual file paths
- Examples still work with current codebase

### Step 5: Verify Index Files

If you added new files, update index files:

- `guides/index.md` - for new guides
- `workflows/index.md` - for new workflows
- `patterns/index.md` - for new patterns
- `README.md` - if structure changed significantly

## Quick Reference

**Minimal update (most common):**
```
1. Identify: What did I change?
2. Map: Which MB file covers this?
3. Update: Add/modify relevant section
4. Validate: Links still work?
```

**After protocol completion:**
```
1. Collect: Gather all "Memory Bank Impact" items from step files
2. Review: Which items need actual updates?
3. Update: Apply changes per Step 3
4. Mark: Check off impact items as done
```

## Examples

### Example 1: New API Endpoint

**Change:** Added `/api/users/[id]/orders` endpoint

**Update:**
1. Open `guides/backend.md`
2. Find "API Routes" section
3. Add new endpoint to route table
4. Add usage example if pattern is new

### Example 2: New Dependency

**Change:** Added `zod` for validation

**Update:**
1. Open `tech_stack.md`
2. Add to dependencies table with version
3. Open `guides/backend.md`
4. Add validation pattern example

### Example 3: Architecture Change

**Change:** Moved from REST to tRPC for internal APIs

**Update:**
1. Open `guides/architecture.md` - update API layer description
2. Open `tech_stack.md` - add tRPC, note REST deprecation
3. Open `patterns/api-design.md` - add tRPC patterns
4. Update `guides/backend.md` - new endpoint patterns

## What NOT to Update

- Don't update docs for experimental/temporary code
- Don't add implementation details that will change
- Don't document bugs or workarounds as patterns
- Don't update if change is being reverted soon

## Related Documentation

- [Development Workflow](./development-workflow.md) - References this in Phase 5
- [Process Protocol](./process-protocol.md) - Uses this for Protocol Completion
- [Create Protocol](./create-protocol.md) - Memory Bank Impact sections
