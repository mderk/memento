---
name: fix-broken-links
description: Validate Memory Bank links and fix broken references automatically
---

# Fix Broken Links in Memory Bank

This skill helps validate and fix broken links in `.memory_bank/` files.

## When to Use

Use this skill when:

-   User explicitly asks to fix broken links
-   User runs `/fix-broken-links` command
-   You need to validate Memory Bank integrity

## Invocation

From target project, run:

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/fix-broken-links/scripts/validate-memory-bank-links.py
```

## Process

### Step 1: Run Validation Script

Execute the validation script to scan Memory Bank in the current project:

```bash
python ./scripts/validate-memory-bank-links.py
```

The script is located in the `scripts/` subdirectory of this skill.

The script will:

-   Scan all `.memory_bank/` files
-   Check all `index.md` links
-   Check all cross-references
-   Report broken links with file paths

**Exit Codes:**

-   `0` - All links valid, no action needed
-   `1` - Broken links found, proceed to fix

### Step 2: Parse Results

If validation fails (exit code 1), the output contains:

-   List of broken index links
-   List of broken cross-references
-   Format: `source_file: [link_text](link_target) → resolved_path`

Example:

```
.memory_bank/guides/index.md: [Testing](./testing.md) → .memory_bank/guides/testing.md
```

### Step 3: Fix Each Broken Link

For each broken link, analyze and fix:

**A. Check if similar file exists:**

-   Use Glob to search for similar file names
-   Example: `testing.md` not found, but `testing-guide.md` exists
-   Action: Update link to correct file

**B. If no similar file exists:**

-   Check if link is to planned but not created file
-   Options:
    1. Remove link entirely (keep text as plain text)
    2. Remove entire section if obsolete
    3. Keep as placeholder with note

**C. Apply fix:**

-   Use Edit tool to update the file
-   Report what was changed

### Step 4: Re-validate

After fixing all links, run validation script again:

```bash
python ./scripts/validate-memory-bank-links.py
```

If still has errors, repeat Step 3 for remaining issues.

### Step 5: Summary

Provide summary:

-   Total links fixed
-   Validation status (✅ passed or ❌ still has issues)
-   List any remaining issues that need manual review

## Examples

### Example 1: Update to similar file

```
Broken: .memory_bank/guides/index.md: [Testing](./testing.md)
Found: .memory_bank/guides/testing-guide.md

Action: Edit .memory_bank/guides/index.md
Change: [Testing](./testing.md) → [Testing](./testing-guide.md)
```

### Example 2: Remove broken link

```
Broken: .memory_bank/README.md: [Old Guide](./guides/deprecated.md)
No similar files found.

Action: Edit .memory_bank/README.md
Change: [Old Guide](./guides/deprecated.md) → Old Guide (deprecated)
```

### Example 3: Remove obsolete section

```
Broken: Multiple links in "## Legacy Workflows" section
All files missing, section is obsolete.

Action: Edit .memory_bank/workflows/index.md
Remove entire "## Legacy Workflows" section
```

## Important Notes

-   **Always read files before editing** - Use Read tool to see context
-   **Preserve intent** - Understand what the link was trying to accomplish
-   **Be conservative** - If unsure, ask user before removing content
-   **Batch edits** - Group similar fixes together for efficiency
-   **Report clearly** - Show before/after for each fix

## Script Location

```
./scripts/validate-memory-bank-links.py
```

It's a standalone Python script that:

-   Requires no dependencies beyond standard library
-   Works without `generation-plan.md`
-   Scans `.memory_bank/` directory automatically
-   Validates both index links and cross-references
