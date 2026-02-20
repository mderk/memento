---
name: analyze-local-changes
description: Analyze local modifications in Memory Bank files, compute hashes, and provide merge strategies
version: 1.0.0
---

# Analyze Local Changes Skill

## Purpose

Detect and analyze local modifications in Memory Bank files by:
1. Computing MD5 hashes and comparing with stored hashes
2. Analyzing WHAT changed (new sections, added lines, modified content)
3. Classifying changes for auto-merge vs manual review
4. Providing structured output for merge operations

## When Claude Uses This Skill

Claude automatically invokes this skill when:

1. **Creating environment**: `/create-environment` needs to compute hashes after generating files
2. **Updating environment**: `/update-environment` needs to detect and analyze local modifications
3. **User requests**: "What local changes were made to Memory Bank?"

## Invocation

From target project, run:

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/analyze-local-changes/scripts/analyze.py <command> [args]
```

Commands: `compute`, `compute-all`, `compute-source`, `detect`, `detect-source-changes`, `analyze`, `analyze-all`, `merge`, `commit-generation`, `recompute-source-hashes`, `update-plan`

## Usage

### Mode 1: Compute Hashes

Compute hashes for files (used after generation).

```bash
python scripts/analyze.py compute .memory_bank/guides/testing.md
python scripts/analyze.py compute-all
```

**Output:**
```json
{
  "status": "success",
  "files": [
    {"path": ".memory_bank/guides/testing.md", "hash": "a1b2c3d4", "lines": 295}
  ]
}
```

### Mode 2: Detect Changes

Compare current hashes with stored hashes in generation-plan.md.

```bash
python scripts/analyze.py detect
```

**Output:**
```json
{
  "status": "success",
  "modified": [".memory_bank/guides/testing.md"],
  "unchanged": [".memory_bank/guides/backend.md"],
  "missing": [],
  "new": [".memory_bank/guides/local-notes.md"],
  "summary": {"total": 25, "modified": 1, "unchanged": 23, "missing": 0, "new": 1}
}
```

### Mode 3: Analyze Changes (Full Analysis)

Analyze WHAT changed in modified files.

```bash
python scripts/analyze.py analyze .memory_bank/guides/testing.md
python scripts/analyze.py analyze-all
```

**Output:**
```json
{
  "status": "success",
  "path": ".memory_bank/guides/testing.md",
  "hash": {
    "stored": "a1b2c3d4",
    "current": "x9y8z7w6"
  },
  "changes": [
    {
      "type": "new_section",
      "header": "### Project-Specific Tests",
      "level": 3,
      "after_section": "## Unit Tests",
      "lines": 15,
      "content_preview": "Tests for domain-specific calculations..."
    },
    {
      "type": "added_lines",
      "in_section": "## Running Tests",
      "lines_added": 3,
      "content": [
        "npm run test:integration",
        "npm run test:e2e"
      ]
    },
    {
      "type": "modified_content",
      "in_section": "## API Patterns",
      "lines_changed": 2,
      "diff": "- Use Next.js patterns for all endpoints.\n+ Use Express patterns for API endpoints.",
      "conflict": true
    }
  ],
  "merge_strategy": {
    "auto_mergeable": [
      {"type": "new_section", "header": "### Project-Specific Tests"},
      {"type": "added_lines", "in_section": "## Running Tests"}
    ],
    "requires_review": [
      {"type": "modified_content", "in_section": "## API Patterns", "reason": "Content conflict"}
    ]
  }
}
```

### Mode 4: Compute Source Hashes

Compute hashes for source prompt/static files in plugin (used during generation).

```bash
python scripts/analyze.py compute-source prompts/memory_bank/README.md.prompt --plugin-root ${CLAUDE_PLUGIN_ROOT}
```

**Output:**
```json
{
  "status": "success",
  "files": [
    {
      "path": "/path/to/plugin/prompts/memory_bank/README.md.prompt",
      "relative_path": "prompts/memory_bank/README.md.prompt",
      "hash": "def456gh",
      "lines": 150
    }
  ]
}
```

### Mode 5: Detect Source Changes

Detect which plugin prompts/statics have changed since last generation.

```bash
python scripts/analyze.py detect-source-changes --plugin-root ${CLAUDE_PLUGIN_ROOT}
```

**Output:**
```json
{
  "status": "success",
  "changed": [
    {
      "generated": ".memory_bank/guides/testing.md",
      "source": "/path/to/plugin/prompts/memory_bank/guides/testing.md.prompt",
      "stored_hash": "abc123",
      "current_hash": "xyz789"
    }
  ],
  "unchanged": [
    {
      "generated": ".memory_bank/README.md",
      "source": "/path/to/plugin/prompts/memory_bank/README.md.prompt"
    }
  ],
  "missing_source": [],
  "no_source_hash": [".memory_bank/old-file.md"],
  "summary": {
    "total": 25,
    "changed": 1,
    "unchanged": 23,
    "missing_source": 0,
    "no_source_hash": 1
  }
}
```

### Mode 6: 3-Way Merge

Merge a locally-modified file with a new plugin version using the Generation Base as reference.

```bash
python scripts/analyze.py merge .memory_bank/guides/testing.md \
  --base-commit abc1234 \
  --new-file /tmp/new-testing.md
```

The script recovers the clean base via `git show <base-commit>:<file>`, reads the local file (with user additions), and merges with the new version.

**Output (no conflicts):**
```json
{
  "status": "merged",
  "merged_content": "# full merged file content...",
  "conflicts": [],
  "stats": {"from_new": 2, "from_local": 1, "unchanged": 5, "user_added": 1, "conflicts": 0}
}
```

**Output (with conflicts):**
```json
{
  "status": "conflicts",
  "merged_content": "# merged with defaults for conflicts...",
  "conflicts": [
    {"section": "## API Patterns", "type": "both_modified", "base": "...", "local": "...", "new": "..."}
  ],
  "stats": {"from_new": 1, "from_local": 0, "unchanged": 4, "user_added": 1, "conflicts": 1}
}
```

**Merge rules (per section):**

| Base | Local | New | Action |
|------|-------|-----|--------|
| A | A | A' | Take new (plugin updated) |
| A | A' | A | Keep local (user modified) |
| A | A' | A'' | Conflict (both modified) |
| A | A | — | Skip (plugin removed, user didn't touch) |
| A | A' | — | Conflict (plugin removed, user modified) |
| — | — | B | Take new (plugin added) |
| — | B | — | Keep local (user added) |
| — | B | B' | Conflict (both added same header) |

Conflict types in output: `both_modified`, `user_deleted`, `both_added`, `plugin_removed_user_modified`.

When conflicts occur, the script defaults to keeping the local version and reports the conflict. Claude should show conflicts to the user for resolution.

### Mode 7: Create Generation Commits

Creates git commits for generated files, handling the two-commit system (base + merge).

**Without merge (first generation or no local changes):**
```bash
python scripts/analyze.py commit-generation --plugin-version 1.3.0
```
Creates two commits: one for generated files, one to update metadata with commit hashes. Sets both `Generation Base` and `Generation Commit` to the same hash.

**With merge (local changes were merged into new versions):**
```bash
python scripts/analyze.py commit-generation --plugin-version 1.3.0 \
  --clean-dir /tmp/memento-clean/
```

The `--clean-dir` contains clean plugin output (before merge). The script:
1. Swaps current files with clean versions from `--clean-dir`
2. Commits clean versions → **Generation Base**
3. Restores merged versions (the files Claude wrote after running `merge`)
4. Commits merged versions → **Generation Commit**
5. Updates `generation-plan.md` Metadata with both hashes

**Output:**
```json
{
  "status": "success",
  "generation_base": "abc1234",
  "generation_commit": "def5678",
  "merge_applied": true,
  "files_merged": [".memory_bank/guides/testing.md", ".memory_bank/workflows/bug-fixing.md"]
}
```

**Why two commits?** Generation Base stores clean plugin output so future 3-way merges can distinguish user additions from plugin content. Without this, previously-merged user additions would be silently dropped on the next update.

### Mode 8: Recompute Source Hashes

Pre-compute hashes for all source files (prompts + statics) into `source-hashes.json`. Run after modifying files in `prompts/` or `static/`.

```bash
python scripts/analyze.py recompute-source-hashes --plugin-root ${CLAUDE_PLUGIN_ROOT}
```

**Output:**
```json
{
  "status": "success",
  "files": 60,
  "written": "source-hashes.json"
}
```

The generated `source-hashes.json` maps relative paths to 8-character MD5 hashes:
```json
{
  "prompts/CLAUDE.md.prompt": "20d52ec2",
  "prompts/memory_bank/README.md.prompt": "77ce72c3",
  "static/memory_bank/workflows/development-workflow.md": "e3c77def"
}
```

Excludes `manifest.yaml` and `__pycache__` directories. Other commands (`compute-source`, `detect-source-changes`, `update-plan`) read from this JSON instead of computing hashes on the fly.

### Mode 9: Update Plan

Batch-update `generation-plan.md` after generating files. Computes file hashes, looks up source hashes from `source-hashes.json`, and updates the markdown table in one call.

```bash
python scripts/analyze.py update-plan .memory_bank/guides/testing.md .memory_bank/README.md --plugin-root ${CLAUDE_PLUGIN_ROOT}
```

**Output:**
```json
{
  "status": "success",
  "updated": [
    {"file": ".memory_bank/guides/testing.md", "lines": 295, "hash": "abc12345", "source_hash": "def67890"},
    {"file": ".memory_bank/README.md", "lines": 127, "hash": "ghi78901", "source_hash": "jkl23456"}
  ]
}
```

For each file: marks `[x]` in Status column, sets Lines, Hash, and Source Hash. If source hash is not found in JSON, falls back to computing from file. Reports warnings for files not found in the plan table.

## Change Types

| Type | Description | Auto-Merge? |
|------|-------------|-------------|
| `new_section` | New `##` or `###` header with content | ✅ Yes |
| `added_lines` | Lines added at end of existing section | ✅ Yes |
| `modified_content` | Existing lines changed | ❌ No (conflict) |
| `deleted_lines` | Lines removed from section | ⚠️ Review |
| `reordered_sections` | Sections moved | ⚠️ Review |

## How It Works

### Hash Computation

```python
import hashlib

def compute_hash(file_path: str, length: int = 8) -> str:
    with open(file_path, 'rb') as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    return md5[:length]
```

### Change Detection

1. Parse `generation-plan.md` to get stored hashes
2. Compute current hash for each file
3. Compare: `stored_hash != current_hash` → modified

### Change Analysis

1. **Get base content**: Regenerate file to temp (or use git history)
2. **Compute diff**: Use `difflib.unified_diff()`
3. **Parse markdown structure**: Find `## Headers` and their content
4. **Classify changes**:
   - New header not in base → `new_section`
   - Lines added after existing content → `added_lines`
   - Lines changed within section → `modified_content`

### Merge Strategy

```python
def determine_merge_strategy(changes):
    auto_merge = []
    manual_review = []

    for change in changes:
        if change['type'] in ['new_section', 'added_lines']:
            auto_merge.append(change)
        else:
            manual_review.append(change)

    return {'auto_mergeable': auto_merge, 'requires_review': manual_review}
```

## Generation Plan Format

The `generation-plan.md` table includes both file hash and source hash:

```markdown
| Status | File | Location | Lines | Hash | Source Hash |
|--------|------|----------|-------|------|-------------|
| [x] | README.md | .memory_bank/ | 127 | abc123 | def456 |
| [x] | testing.md | .memory_bank/guides/ | 295 | ghi789 | jkl012 |
```

- **Hash**: MD5 hash of the generated file (detects local modifications)
- **Source Hash**: MD5 hash of the source prompt/static (detects plugin updates)

## Integration with Commands

### /create-environment

```markdown
Phase 2: For each generated file:
1. Generate file → write to target AND /tmp/memento-clean/<path>
2. If merge mode: analyze.py merge <target> --base-commit <old_base> --new-file /tmp/...
3. Write merged_content (or clean if no merge) to target

After all batches complete:
  analyze.py update-plan <all file paths> --plugin-root ...
  (computes hashes, looks up source hashes from source-hashes.json, updates plan)

Phase 3: After all files:
  analyze.py commit-generation --plugin-version X.Y.Z [--clean-dir /tmp/memento-clean/]
```

### /update-environment

```markdown
Step 0.2: Detect changes
1. analyze.py detect-source-changes --plugin-root ...  → plugin updates (reads source-hashes.json)
2. analyze.py detect                                    → local modifications

Step 4: For each file to update:
1. Generate/copy new version → write to target AND /tmp/memento-clean/<path>
2. If locally modified: analyze.py merge <target> --base-commit <base> --new-file /tmp/...
3. If conflicts: show to user, resolve
4. Write merged_content to target

After all batches:
  analyze.py update-plan <all file paths> --plugin-root ...

Step 5: After all files:
  analyze.py commit-generation --plugin-version X.Y.Z [--clean-dir /tmp/memento-clean/]
```

## Example Scenarios

### Scenario 1: New Project Section Added

User added project-specific testing section to testing.md:

```
Input: testing.md with new "### Integration Tests" section

Analysis:
{
  "changes": [
    {
      "type": "new_section",
      "header": "### Integration Tests",
      "after_section": "## Unit Tests",
      "lines": 15
    }
  ],
  "merge_strategy": {
    "auto_mergeable": [{"type": "new_section", ...}],
    "requires_review": []
  }
}

Result: Can auto-merge by inserting section after "## Unit Tests"
```

### Scenario 2: Conflicting Change

User modified existing API patterns section:

```
Input: backend.md with changed "## API Patterns" content

Analysis:
{
  "changes": [
    {
      "type": "modified_content",
      "in_section": "## API Patterns",
      "diff": "- Use Next.js patterns\n+ Use FastAPI patterns",
      "conflict": true
    }
  ],
  "merge_strategy": {
    "auto_mergeable": [],
    "requires_review": [{"type": "modified_content", ...}]
  }
}

Result: Requires user decision - keep local or use plugin version
```

## Script Location

```
./scripts/analyze.py
```

## Dependencies

**All built-in (no pip install required):**
- `hashlib` - MD5 computation
- `difflib` - Diff computation
- `subprocess` - Git operations (merge, commit-generation)
- `json` - JSON output
- `re` - Markdown parsing
- `pathlib` - Path handling
- `argparse` - CLI arguments

## Exit Codes

- `0`: Success
- `1`: File not found
- `2`: generation-plan.md not found
- `3`: Invalid mode/arguments

## Notes

- **Mostly read-only**: `merge` and `commit-generation` are the only commands that modify files/git
- **Cross-platform**: Works on macOS, Linux, Windows
- **No external dependencies**: Standard library only (requires git for `merge` and `commit-generation`)
- **Structured output**: JSON for easy parsing
- **Smart classification**: Distinguishes safe vs conflict changes
- **Two-commit system**: `commit-generation` preserves clean plugin base for future 3-way merges
