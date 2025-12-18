---
description: Update specific Memory Bank files or groups based on filter criteria
---

# Update Environment Files

This command allows selective update/regeneration of Memory Bank files based on filter criteria.

## Usage

User can specify what to regenerate:

1. **Specific file**: `testing-workflow.md`
2. **File pattern**: `*-workflow.md` or `workflows/*.md`
3. **Category**: `workflows`, `guides`, `agents`, or `commands`
4. **Multiple files**: `code-review-workflow.md, testing-workflow.md`
5. **All files**: `all`

## Process

### Step 1: Parse Filter Criteria

Parse user's input to determine which files to regenerate:

**Examples:**
```
"testing-workflow.md" → workflows/testing-workflow.md
"workflows" → all files in .memory_bank/workflows/
"*-workflow.md" → all workflow files
"guides" → all files in .memory_bank/guides/
"code-review-workflow.md, agent-orchestration.md" → multiple specific files
"all" → entire Memory Bank
```

### Step 2: Verify Project Context

1. Check if `.memory_bank/project-analysis.json` exists
2. Check if `.memory_bank/generation-plan.md` exists

**If files don't exist:**
```
Error: No generation context found.
Please run /create-environment first to create generation plan.
```

**If files exist**: Continue to Step 3

### Step 3: Identify Files to Regenerate

Based on filter criteria and generation plan:

1. **Read generation plan**: `.memory_bank/generation-plan.md`
2. **Filter by criteria**:
   - If specific file(s): Match exact names
   - If pattern: Use glob matching (`*-workflow.md` matches all workflows)
   - If category: Match by target_path (e.g., `workflows/` matches `.memory_bank/workflows/`)
   - If "all": Include all files from plan

3. **Build regeneration list**:
   ```markdown
   Files to regenerate:
   - [ ] code-review-workflow.md (.memory_bank/workflows/)
   - [ ] testing-workflow.md (.memory_bank/workflows/)

   Total: 2 files
   ```

4. **Show preview to user**:
   ```
   Found 2 files matching criteria "workflows":

   1. code-review-workflow.md (workflows/)
   2. testing-workflow.md (workflows/)

   These files will be OVERWRITTEN. Proceed? Reply 'Yes' to continue.
   ```

5. **Wait for user confirmation** before proceeding

### Step 4: Regenerate Files

After user confirms with "Yes" (or "Go", "Continue", "Proceed"):

1. **Process in batches**: Use Task tool to regenerate 5 files at a time

2. **For each batch**:
   - Regenerate files using generation plan
   - Update `.memory_bank/` files
   - Mark completed in `.memory_bank/generation-plan.md`

3. **Update generation plan**: Mark regenerated files as `[x]` in `.memory_bank/generation-plan.md`

4. **Report progress**:
   ```
   Batch 1/1 complete:
   ✓ code-review-workflow.md regenerated (63 lines)
   ✓ testing-workflow.md regenerated (59 lines)

   Regeneration complete! 2/2 files updated.
   ```

### Step 5: Verify Results

After regeneration:

1. **Show summary**:
   ```markdown
   Regeneration Summary:

   ✓ 2 files regenerated successfully
   ✗ 0 files failed

   Files updated:
   - .memory_bank/workflows/code-review-workflow.md (63 lines)
   - .memory_bank/workflows/testing-workflow.md (59 lines)

   Next steps:
   - Review regenerated files for quality
   - Run validation: /validate-links or /optimize-memory-bank
   - Test with AI agents to ensure correctness
   ```

2. **Offer validation**: "Would you like to validate links in regenerated files? Reply 'Yes' to run validation."

## Filter Criteria Examples

### Specific Files

```bash
# Regenerate single file
/update-environment testing-workflow.md

# Regenerate multiple files
/update-environment code-review-workflow.md, testing-workflow.md, agent-orchestration.md
```

### Categories

```bash
# Regenerate all workflows
/update-environment workflows

# Regenerate all guides
/update-environment guides

# Regenerate all agents
/update-environment agents
```

### Patterns

```bash
# All workflow files
/update-environment *-workflow.md

# All files in workflows directory
/update-environment workflows/*.md

# All files with "test" in name
/update-environment *test*.md
```

### All Files

```bash
# Regenerate entire Memory Bank
/update-environment all
```

## Use Cases

### After Updates

```
Developer: Updated workflow documentation. Regenerate all workflows.

/update-environment workflows

AI: Found 7 files matching criteria "workflows":
1. agent-orchestration.md
2. code-review-workflow.md
3. create-prd.md
4. create-spec.md
5. feature-development.md
6. generate-tasks.md
7. testing-workflow.md

Proceed? Reply 'Yes' to continue.

Developer: Yes

AI: Regenerating workflows...
✓ All 7 workflows regenerated successfully.
```

### After Updating Single File

```
Developer: Updated testing workflow documentation.

/update-environment testing-workflow.md

AI: Found 1 file matching criteria:
1. testing-workflow.md (workflows/)

Proceed?

Developer: Yes

AI: ✓ testing-workflow.md regenerated (59 lines)
```

### Testing Changes

```
Developer: Testing improvements. Regenerate code-review workflow.

/update-environment code-review-workflow.md

AI: [Regenerates and shows diff]
Before: 285 lines
After: 63 lines
Changes: Removed embedded checklists, added references to guides
```

## Safety Checks

Before regeneration:

1. ✓ Verify `.memory_bank/project-analysis.json` exists
2. ✓ Verify `.memory_bank/generation-plan.md` exists
3. ✓ Confirm files match filter criteria
4. ✓ Show preview of files to be overwritten
5. ✓ Wait for explicit user confirmation

After regeneration:

1. ✓ Update generation plan with `[x]` marks
2. ✓ Report file sizes and line counts
3. ✓ Offer link validation
4. ✓ Suggest testing with AI agents

## Error Handling

**No generation context:**
```
Error: Cannot regenerate without project context.
Run /create-environment first to analyze project and create generation plan.
```

**No matching files:**
```
Error: No files match criteria "xyz".

Available categories: workflows, guides, agents, commands
Available files: [list from generation-plan.md]
```

**User cancels:**
```
Regeneration cancelled by user.
No files were modified.
```

**Generation fails:**
```
Warning: 1 file failed to regenerate:
✗ testing-workflow.md - Error: [error message]

Retry failed file? Reply 'Yes' to retry.
```

## Related Commands

- `/create-environment` - Initial Memory Bank generation
- `/optimize-memory-bank` - Analyze and remove redundancy
- `/fix-broken-links` - Find and fix broken links
- `/validate-links` - Validate all internal links

## Implementation Notes

1. **Batch processing**: Process 5 files at a time
2. **Use existing project analysis**: Don't re-analyze project
3. **Update generation plan**: Mark files as completed after regeneration
4. **Preserve manual edits**: Warn if files have manual edits (check git status)
5. **Parse filter flexibly**: Handle typos, case-insensitive matching
6. **Show preview**: Clear preview before any overwrites
7. **Report progress**: Update during batch generation
8. **Offer follow-up**: Validation, testing options after completion
