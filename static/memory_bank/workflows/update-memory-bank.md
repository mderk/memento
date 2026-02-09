# Rule: Update Memory Bank

## Goal

Keep Memory Bank documentation synchronized with code changes.

## When to Use

-   After completing features (code review passed)
-   After architectural changes
-   After adding/removing dependencies
-   After changing established patterns
-   After protocol completion (collect Findings and Memory Bank Impact)

## What NOT to Update

These rules apply to all updates — both ad-hoc and after protocol completion:

-   Experimental or temporary code
-   Implementation details that will change
-   Bugs or workarounds (don't document as patterns)
-   Changes being reverted soon
-   What is already clear from reading the code
-   Trial-and-error process (keep the conclusion, not the journey)

## Process

### Step 1: Identify What Changed

Review your changes and categorize:

| Change Type        | Examples                                             |
| ------------------ | ---------------------------------------------------- |
| API changes        | New endpoints, modified responses, deprecated routes |
| Component patterns | New component structures, state management changes   |
| Dependencies       | Added/removed packages, version upgrades             |
| Architecture       | New services, changed data flow, infrastructure      |
| Patterns           | New coding patterns, conventions, best practices     |

### Step 2: Map Changes to Memory Bank Files

| Change Type               | Target Files                                    |
| ------------------------- | ----------------------------------------------- |
| API routes, backend logic | `guides/backend.md`, `patterns/api-design.md`   |
| Frontend components       | `guides/frontend.md`, `guides/visual-design.md` |
| Dependencies, stack       | `tech_stack.md`                                 |
| Architecture decisions    | `guides/architecture.md`                        |
| Testing patterns          | `guides/testing.md`                             |
| New workflows             | `workflows/` directory                          |
| New patterns              | `patterns/` directory                           |

### Step 3: Check Existing Content

Before writing, read the target Memory Bank file and compare:

| Situation                      | Action                                |
| ------------------------------ | ------------------------------------- |
| Already documented and current | Skip — nothing to do                  |
| Documented but outdated        | Update existing section in place      |
| Contradicts existing content   | Replace old with new, note the change |
| Not documented yet             | Add to appropriate section            |

### Step 4: Update Affected Files

For each identified file:

1. Identify section to update
2. Make minimal, focused changes
3. Preserve existing structure and style

**Update principles:**

-   Add new information, don't remove unless obsolete
-   Keep examples current and working
-   Update version numbers if dependencies changed
-   Add cross-references to related docs

### Step 5: Validate Links

Run link validation to ensure no broken references:

```bash
/memento:fix-broken-links
```

Or manually check:

-   Internal links `[text](./path)` resolve correctly
-   Code references match actual file paths
-   Examples still work with current codebase

### Step 6: Verify Index Files

If you added new files, update index files:

-   `guides/index.md` - for new guides
-   `workflows/index.md` - for new workflows
-   `patterns/index.md` - for new patterns
-   `README.md` - if structure changed significantly

## Quick Reference

```
1. Identify: What did I change?
2. Map: Which MB file covers this?
3. Check: Already documented?
4. Update: Add/modify relevant section
5. Validate: Links still work?
```

## After Protocol Completion

When [Process Protocol](./process-protocol.md) reaches Protocol Completion, follow this extended process instead of the standard one above.

### 1. Collect

Follow links in plan.md Progress to find all step files. Gather from each:

-   `## Memory Bank Impact` — pre-planned update targets
-   `## Findings` — runtime discoveries
-   `_context/findings.md` — promoted cross-step findings (if exists)

### 2. Triage

Apply [What NOT to Update](#what-not-to-update) rules, plus filter findings specifically:

**Keep** only what:

-   Will affect future decisions (architectural choices, constraints)
-   Is not obvious from code (gotchas, implicit system behavior)
-   Is a repeatable pattern or convention

**Discard** additionally:

-   Task-specific details ("mocked service X for testing")
-   Temporary workarounds that will be cleaned up

### 3. Transform

Rewrite findings as knowledge, not history:

| Finding (raw)                                                           | Memory Bank entry (distilled)                                    |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Tried redis for sessions → switched to postgres (deployment complexity) | Sessions use postgres; redis rejected for deployment complexity  |
| `[GOTCHA]` Auth middleware caches tokens for 5min                       | Auth middleware: 5min token cache — account for in refresh logic |
| `[REUSE]` Found `parseFilter()` utility in shared/                      | Filter parsing: use `shared/parseFilter()`, don't reimplement    |

### 4. Apply

Follow the standard Process above (Steps 2–6) with the triaged and transformed items.

### 5. Mark

Check off impact items as done in step files.

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

## Related Documentation

-   [Development Workflow](./development-workflow.md) - References this in Phase 5
-   [Process Protocol](./process-protocol.md) - Uses this for Protocol Completion
-   [Create Protocol](./create-protocol.md) - Memory Bank Impact and Findings sections
