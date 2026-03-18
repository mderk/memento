# Rule: Doc Gardening (Memory Bank Garbage Collection)

## Goal

Keep the Memory Bank **legible, accurate, and low-drift** over time — so both humans and AI agents can rely on it as the system of record.

This is the documentation equivalent of garbage collection: small, frequent cleanups prevent entropy from compounding.

## When to Run

- **Weekly (recommended)**: 10–20 minutes of upkeep
- **Before major refactors/releases**: reduce confusion and broken references
- **After large protocol work**: promote findings into durable docs

## Entry Point

Run:

- `/doc-gardening`

## Process

### Step 1: Run Link Integrity Checks

Fix broken internal links first (broken links destroy navigability).

- Run: `/memento:fix-broken-links`
- If a link points to a file that shouldn’t exist: remove the link and replace with the correct reference.

### Step 2: Reduce Redundancy (Keep Docs “Map-First”)

Remove duplicate explanations and long repeated checklists.

- Optional: run `/memento:optimize-memory-bank`
- Prefer: **reference-first** (workflow → guide → pattern), not “every file explains everything”.

### Step 3: Validate the “Control Surface”

Ensure the README and indexes reflect how the project is actually operated.

Check:

- `.memory_bank/README.md` skill list matches available skills
- `guides/index.md` and `patterns/index.md` are complete and accurate (if present)

### Step 4: Freshness Pass (Reality Check)

Skim for statements that are likely to rot:

- “Always”, “never”, “the only way”, “we don’t use X”
- hard-coded paths/commands that might have changed
- outdated stack/tooling references

Update or delete anything that no longer matches current reality.

### Step 5: Promote Durable Knowledge

Convert runtime discoveries into reusable knowledge:

- From protocol step `## Findings` → distilled entries in guides/patterns
- Update architecture or patterns only when it changes future decisions

Reference: [Update Memory Bank](./update-memory-bank.md) (protocol completion section)

## Output

After doc gardening, report a short summary:

- What you fixed (broken links, outdated sections, index updates)
- What you removed (redundant or stale content)
- Any follow-up debt deferred (with references/paths)

## Related Documentation

- [Update Memory Bank](./update-memory-bank.md)
- `/develop` workflow
