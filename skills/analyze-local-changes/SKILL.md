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

Commands: `compute`, `compute-all`, `compute-source`, `detect`, `detect-source-changes`, `analyze`, `analyze-all`

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
After writing each file:
1. Compute source hash: python scripts/analyze.py compute-source <prompt> --plugin-root ${CLAUDE_PLUGIN_ROOT}
2. Generate file from prompt
3. Compute file hash: python scripts/analyze.py compute <file>
4. Update generation-plan.md with both hashes
```

### /update-environment

```markdown
Step 0.2.4: Detect Plugin Changes
1. Invoke: python scripts/analyze.py detect-source-changes --plugin-root ${CLAUDE_PLUGIN_ROOT}
2. Get list of files whose source prompts have changed
3. These files need regeneration

Step 0.2.5: Detect Local Modifications
1. Invoke: python scripts/analyze.py detect
2. Get list of locally modified files

Step 4: For each file needing regeneration:
1. If also locally modified: Invoke analyze to get merge strategy
2. Regenerate from new prompt
3. Auto-merge local changes where safe
4. Ask user about conflicts
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

- **Non-invasive**: Read-only, no file modifications
- **Cross-platform**: Works on macOS, Linux, Windows
- **No external dependencies**: Standard library only
- **Structured output**: JSON for easy parsing
- **Smart classification**: Distinguishes safe vs conflict changes
