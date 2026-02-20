---
name: defer
description: Defer an out-of-scope finding to the backlog. Use when a bug, tech debt, idea, or risk is discovered but not appropriate to solve now.
argument-hint: <title>
---

# Defer Finding to Backlog

## Script

```
${CLAUDE_PLUGIN_ROOT}/skills/defer/scripts/defer.py
```

All commands output JSON. The script bootstraps `.backlog/` automatically on first use.

## Step 1: Determine context

Detect where `/defer` was called from:

- **Inside a protocol step** → origin is the step file path (e.g. `.protocols/0001-feature/03-api.md`)
- **During code review triage** → origin is `code-review`
- **Standalone** → ask the user for origin or leave empty

## Step 2: Gather details

From `$ARGUMENTS` and conversation context, determine:

| Field | Required | How to get |
|-------|----------|------------|
| title | yes | From `$ARGUMENTS`, or ask |
| type | yes | `bug`, `debt`, `idea`, or `risk` — infer from context, confirm if ambiguous |
| priority | yes | `p0`–`p3` — infer from severity, confirm if ambiguous |
| area | no | Freeform domain tag (e.g. `batch`, `map`, `bot`, `auth`) — infer from context |
| effort | no | `xs`/`s`/`m`/`l`/`xl` — usually filled later during triage, not at creation |
| origin | no | Auto-detected from step 1 |
| description | no | Brief explanation of what was found |

## Step 3: Create the backlog item

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/defer/scripts/defer.py create \
  --title "<title>" --type <type> --priority <priority> \
  --area "<area>" --effort <effort> \
  --origin "<origin>" --description "<description>"
```

Returns JSON:
```json
{"action": "create", "slug": "auth-coupling", "path": ".backlog/items/auth-coupling.md", ...}
```

## Step 4: Link from origin

**If inside a protocol step** — insert a `[DEFER]` line into the step's Findings:

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/defer/scripts/defer.py link-finding \
  <step-file-path> <slug> "<title>"
```

**If during code review** — include the returned `path` in the triage table Rationale column. Do not run link-finding.

**If standalone** — no linking needed.

## Step 5: Report

Tell the user what was created:
- Item path from the JSON `path` field
- Type and priority
- Where it was linked (if applicable)

## Other operations

```bash
# List active items (with optional filters)
python ${CLAUDE_PLUGIN_ROOT}/skills/defer/scripts/defer.py list --status open
python ${CLAUDE_PLUGIN_ROOT}/skills/defer/scripts/defer.py list --type bug --area bot
python ${CLAUDE_PLUGIN_ROOT}/skills/defer/scripts/defer.py list --priority p1

# Generate a view (saved dashboard grouped by a field)
python ${CLAUDE_PLUGIN_ROOT}/skills/defer/scripts/defer.py view --group-by priority -o .backlog/views/by-priority.md
python ${CLAUDE_PLUGIN_ROOT}/skills/defer/scripts/defer.py view --group-by area -o .backlog/views/by-area.md
python ${CLAUDE_PLUGIN_ROOT}/skills/defer/scripts/defer.py view --group-by type -o .backlog/views/by-type.md

# Filtered view (e.g. only batch items grouped by type)
python ${CLAUDE_PLUGIN_ROOT}/skills/defer/scripts/defer.py view --group-by type --area batch

# Close and archive a resolved item
python ${CLAUDE_PLUGIN_ROOT}/skills/defer/scripts/defer.py close <slug>

# Bootstrap .backlog/ without creating an item
python ${CLAUDE_PLUGIN_ROOT}/skills/defer/scripts/defer.py bootstrap
```
