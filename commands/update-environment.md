---
description: Update Memory Bank files after tech stack changes or plugin updates with smart detection
---

# Update Environment Files

> **Note: File Access Permissions**
>
> During updates, Claude Code will request permission to read plugin files (prompts, templates, manifests). This is expected - plugins don't have automatic read access to their own directories. You can:
> - Approve each request as it appears
> - Add `Read(~/.claude/plugins/**)` to your `.claude/settings.json` to avoid repeated prompts
>
> See [README - File Access Permissions](https://github.com/mderk/memento#file-access-permissions) for details.

This command allows selective update/regeneration of Memory Bank files. It can:

1. **Detect tech stack changes** - Compare current project state with initial analysis
2. **Find plugin updates** - Discover new/removed prompts in the plugin
3. **Detect local modifications** - Identify files modified since last generation (via hash comparison)
4. **Smart merge** - Preserve local changes when regenerating files
5. **Smart recommendations** - Suggest which files need updating based on detected changes
6. **Manual selection** - Update specific files, patterns, or categories

## Usage

User can specify what to regenerate:

1. **Specific file**: `testing-workflow.md`
2. **File pattern**: `*-workflow.md` or `workflows/*.md`
3. **Category**: `workflows`, `guides`, `agents`, or `commands`
4. **Multiple files**: `code-review-workflow.md, testing-workflow.md`
5. **All files**: `all`
6. **Smart update**: `auto` or `detect` - Analyze project changes and plugin updates, suggest what to regenerate

## Process

### Step 0: Detect Changes (Auto Mode)

When user runs `/update-environment auto` or `/update-environment detect`:

#### 0.1: Analyze Current Project State

1. **Re-scan project using detect-tech-stack skill**:
   - Invoke `detect-tech-stack` skill to detect current project state
   - Skill outputs JSON with: backend/frontend frameworks with versions, databases, test frameworks, libraries, project structure

2. **Load original state**:
   - Read `.memory_bank/project-analysis.json`
   - Extract original tech stack values

3. **Compare states**:
   ```
   Original State (from project-analysis.json):
   - Backend: Django 4.2
   - Frontend: React 18.2
   - Database: PostgreSQL 15
   - Test Framework: pytest, jest

   Current State (detected now):
   - Backend: Django 5.0  ← VERSION CHANGED
   - Frontend: React 18.2
   - Database: PostgreSQL 16  ← VERSION CHANGED
   - Test Framework: pytest, jest, playwright  ← NEW FRAMEWORK
   ```

4. **Identify significant changes**:
   - **Framework change** (e.g., Django → FastAPI): HIGH impact - regenerate all backend files
   - **Major version change** (e.g., React 17 → 18): MEDIUM impact - review affected files
   - **New framework added** (e.g., added Playwright): MEDIUM impact - regenerate testing files
   - **Minor version change** (e.g., Django 4.2 → 5.0): LOW impact - optional update
   - **Library added/removed**: LOW impact - update relevant guides

5. **Determine affected files**:
   Based on changes detected, build list of files that should be updated:

   ```markdown
   ## Tech Stack Changes Detected

   ### High Impact Changes:
   None

   ### Medium Impact Changes:
   - ✓ Playwright test framework added
     → Affected files: testing.md, testing-workflow.md

   ### Low Impact Changes:
   - Django 4.2 → 5.0 (minor version bump)
     → Affected files: backend.md
   - PostgreSQL 15 → 16 (minor version bump)
     → Affected files: backend.md

   ### Recommendation:
   Regenerate 3 files to reflect current tech stack:
   - .memory_bank/guides/testing.md
   - .memory_bank/workflows/testing-workflow.md
   - .memory_bank/guides/backend.md
   ```

#### 0.2: Check for Plugin Updates

1. **Detect source changes** (prompts/statics modified since last generation):
   - Invoke `analyze-local-changes` skill with `detect-source-changes --plugin-root ${CLAUDE_PLUGIN_ROOT}`
   - Skill compares stored Source Hash with current prompt hash
   - Output:
     ```json
     {
       "changed": [{"generated": ".memory_bank/guides/testing.md", "source": "...", "stored_hash": "abc", "current_hash": "xyz"}],
       "unchanged": [...],
       "no_source_hash": [".memory_bank/old-file.md"]
     }
     ```
   - Files in "changed" list need regeneration due to plugin updates

2. **Scan plugin prompts** (for new prompts):
   - Read all files in `${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/*.prompt`
   - Extract file names and target paths from frontmatter

3. **Load generation plan**:
   - Read `.memory_bank/generation-plan.md`
   - Extract list of files that were generated

3. **Compare lists**:
   ```
   Plugin Prompts (40 files):
   ✓ CLAUDE.md
   ✓ README.md
   ✓ product_brief.md
   ...
   ✓ research-analyst.md (agents)  ← NEW FILE
   ✓ security-reviewer.md (agents)  ← NEW FILE

   Generation Plan (37 files):
   ✓ CLAUDE.md
   ✓ README.md
   ✓ product_brief.md
   ...
   ✗ research-analyst.md - NOT IN PLAN
   ✗ security-reviewer.md - NOT IN PLAN
   ```

4. **Identify new prompts**:
   ```markdown
   ## Plugin Updates Detected

   Found 2 new prompt files not in generation plan:

   1. **research-analyst.md** (agents/)
      - Purpose: Research and analyze information from web pages and documentation
      - Conditional: null (applies to all projects)
      → Recommendation: ADD

   2. **security-reviewer.md** (agents/)
      - Purpose: Security vulnerability scanning and best practices
      - Conditional: null (applies to all projects)
      → Recommendation: ADD
   ```

5. **Check for new/updated static files**:
   - Read `${CLAUDE_PLUGIN_ROOT}/static/manifest.yaml`
   - Load stored hashes from `.memory_bank/generation-plan.md`
   - For each file in manifest (that passes conditional):
     - Look up current plugin Source Hash from `source-hashes.json` (or compute via `analyze-local-changes compute-source` as fallback)
     - Check if target file exists in project directory
     - **If missing** → mark as "NEW static file"
     - **If exists** → apply decision matrix:

       | Local modified? | Plugin updated? | Action |
       |---|---|---|
       | No | No | UP TO DATE — skip |
       | No | Yes | SAFE OVERWRITE — copy new version |
       | Yes | No | LOCAL ONLY — keep user's version |
       | Yes | Yes | MERGE NEEDED — 3-way merge |

       Detection:
       - Local modified = stored Hash ≠ current file hash
       - Plugin updated = stored Source Hash ≠ current plugin source hash

   - Build report:
     ```markdown
     ## Static Files Updates

     New (1): development-workflow.md
     Safe overwrite (2): code-review-workflow.md, testing-workflow.md
     Merge needed (1): bug-fixing.md ⚠️ (local changes + plugin update)
     Up to date (8): [skipped]
     Local only (1): commit-message-rules.md (keep)

     → Recommendation: Copy new, overwrite safe, merge conflicts
     ```

6. **Check for obsolete files** (files in MB but removed from plugin):
   - Scan all files in `.memory_bank/` directory
   - For each file, check if corresponding prompt exists in plugin:
     - Memory Bank files: `${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/{filename}.prompt`
     - Static files: Check `${CLAUDE_PLUGIN_ROOT}/static/manifest.yaml`
   - If file exists in MB but NOT in plugin → mark as "OBSOLETE"
   - Build list of obsolete files:
     ```markdown
     ## Obsolete Files Detected

     Found 2 files in Memory Bank with no matching plugin prompt:

     1. **feature-workflow.md** (workflows/)
        - No prompt: ${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/workflows/feature-workflow.md.prompt
        → Recommendation: DELETE (removed from plugin)

     2. **current_tasks.md** (.memory_bank/)
        - No prompt: ${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/current_tasks.md.prompt
        → Recommendation: DELETE (removed from plugin)

     Note: These files may contain project-specific content. Review before deleting.
     ```

#### 0.2.5: Detect Local Modifications

Before presenting recommendations, check which files have been modified locally since last generation.

1. **Read Generation Base** from generation-plan.md Metadata section (fall back to `Generation Commit` if no Base)

2. **Invoke `analyze-local-changes` skill** with `detect` command to find modified files (hash comparison)

3. **Parse skill output**:
   ```json
   {
     "status": "success",
     "modified": [".memory_bank/guides/testing.md"],
     "unchanged": [".memory_bank/guides/backend.md"],
     "missing": [],
     "new": [],
     "summary": {"total": 25, "modified": 1, "unchanged": 24}
   }
   ```

4. **Note modified files for merge** during Step 4:
   - Modified files will be merged using `analyze-local-changes merge` (which handles base recovery automatically)
   - If no Generation Base/Commit available: warn that 3-way merge unavailable

5. **Build local modifications report**:
   ```markdown
   ## Local Modifications Detected

   ⚠️ 2 of 5 files to update have local modifications:

   1. **testing.md** (guides/)
      - Generated hash: a1b2c3d4
      - Current hash: x9y8z7w6
      - Status: MODIFIED LOCALLY

   2. **backend.md** (guides/)
      - Generated hash: e5f6g7h8
      - Current hash: p0q1r2s3
      - Status: MODIFIED LOCALLY

   3. **architecture.md** (guides/)
      - Hash match: ✓ unchanged

   Local changes will be preserved during regeneration (see Merge Strategy).
   ```

#### 0.3: Present Recommendations

Combine findings from 0.1, 0.2, and 0.2.5:

```markdown
# Update Recommendations

## 1. Tech Stack Changes
3 files need updates due to technology changes:
- testing.md (Playwright added)
- testing-workflow.md (Playwright added)
- backend.md (Django 5.0, PostgreSQL 16)

## 2. New Plugin Prompts
2 new agent files available:
- research-analyst.md (NEW)
- security-reviewer.md (NEW)

## 3. Missing Static Files
1 static file missing from project:
- development-workflow.md (MANDATORY workflow)

## 4. Obsolete Files
2 files no longer in plugin:
- feature-workflow.md (REMOVED from plugin)
- current_tasks.md (REMOVED from plugin)

## 5. Local Modifications
⚠️ 2 files have local changes that will be preserved:
- testing.md (12 lines added locally)
- backend.md (5 lines added locally)

## 6. Suggested Actions

Option A: Update affected files only (3 files)
→ Regenerate testing.md, testing-workflow.md, backend.md
→ Local changes will be merged automatically

Option B: Add new prompts only (2 files)
→ Generate research-analyst.md and security-reviewer.md

Option C: Update static files (X new, Y overwrite, Z merge)
→ Copy new files, overwrite unchanged, 3-way merge where local changes exist

Option D: Delete obsolete files (2 files)
→ Remove feature-workflow.md and current_tasks.md

Option E: All updates (A + B + C + D)
→ Update + add new + copy static + delete obsolete

Option F: Full regeneration (all files)
→ /update-environment all

Which option would you like? Reply with A, B, C, D, E, or F.
```

7. **Wait for user choice**, then proceed based on selection:
   - **Option A**: Continue to Step 1 with filter = affected files only (with merge)
   - **Option B**: Continue to Step 1 with filter = new prompts only
   - **Option C**: Update static files using Step 4A flow:
     - Apply decision matrix for each file (new/overwrite/keep/merge)
     - For merge conflicts: show diff, ask user per-conflict
     - Skip to Step 5 after completion
   - **Option D**: Delete obsolete files:
     - For each obsolete file, run: `rm .memory_bank/[path]/[file]`
     - Remove from generation-plan.md
     - Report: `🗑️ Deleted [filename] (obsolete)`
   - **Option E**: Execute A + B + C + D in sequence
   - **Option F**: Continue to Step 1 with filter = "all" (full regeneration with merge)

#### 0.4: Update project-analysis.json

If user proceeds with any option:

1. **Update project analysis** with current detected state:
   ```bash
   # Backup old analysis
   cp .memory_bank/project-analysis.json .memory_bank/project-analysis.json.backup

   # Write new analysis with current tech stack
   ```

2. **Add new prompts to generation plan**:
   - If new plugin files were detected and user wants to add them
   - Append to `.memory_bank/generation-plan.md` with appropriate priority
   - Mark as `[ ]` (pending generation)

3. **Report**:
   ```
   ✓ Updated project-analysis.json with current tech stack
   ✓ Added 2 new files to generation plan

   Proceeding with regeneration...
   ```

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

4. **Show preview to user** (with local change indicators):
   ```
   Found 3 files matching criteria "workflows":

   1. code-review-workflow.md (workflows/) — safe overwrite
   2. testing-workflow.md (workflows/) — safe overwrite
   3. bug-fixing.md (workflows/) ⚠️ local changes → will merge

   Proceed? Reply 'Yes' to continue.
   ```

5. **Wait for user confirmation** before proceeding

### Step 4: Update Files

After user confirms with "Yes" (or "Go", "Continue", "Proceed"):

**Read Generation Base** from generation-plan.md Metadata (fall back to `Generation Commit` if no Base).

#### 4A: Update Static Files

For each static file that needs updating (from Step 0.2 section 5):

1. **Read new version** from `${CLAUDE_PLUGIN_ROOT}/static/[source]`
2. **Save clean version** to `/tmp/memento-clean/<target_path>`
3. **Apply decision matrix**:

   - **NEW** (missing locally): Write to target, compute hash. Report: `📋 Copied [filename] (new static)`
   - **SAFE OVERWRITE** (no local changes): Overwrite target. Report: `📋 Updated [filename] (static)`
   - **LOCAL ONLY** (no plugin update): Skip. Report: `⏭️ Kept [filename] (local changes, no plugin update)`
   - **MERGE NEEDED** (both changed):
     - Invoke `analyze-local-changes merge <target> --base-commit <generation_base> --new-file /tmp/memento-clean/<path>`
     - If `status == "merged"`: write `merged_content` to target
     - If `status == "conflicts"`: show each conflict to user (Keep local / Use plugin / Skip), apply choices, write result
     - If `status == "error"` (no git): show diff(local, new), ask user per-section
     - Report: `🔀 Merged [filename] (X user changes preserved)`

4. **Update generation plan**: Invoke `analyze-local-changes update-plan <all updated targets> --plugin-root ${CLAUDE_PLUGIN_ROOT}` to batch-update Hash, Source Hash, Lines and mark `[x]`

#### 4B: Regenerate Prompt-Based Files

Process in batches (5 files at a time) using Task tool.

For each file in batch:

   a. **Find and read prompt template**:
      - Determine prompt path: `${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/{filename}.prompt`
      - Read the prompt file, report: `📝 Regenerating [filename]...`

   b. **Generate content** following prompt instructions (project-analysis.json for input, no placeholders)

   c. **Save clean version** to `/tmp/memento-clean/<target_path>`

   d. **Merge** (if file has local modifications from Step 0.2.5):
      - Invoke `analyze-local-changes merge <target> --base-commit <generation_base> --new-file /tmp/memento-clean/<path>`
      - If conflicts: show to user, resolve
      - Write `merged_content` to target
      - Report: `🔀 Merged local changes into [filename]`
      - If no local modifications: write clean version to target

   e. **Check redundancy** (MANDATORY, inline - no nested subagent):
      - Report: `🔍 Checking [filename] for redundancy...`
      - Count lines in generated file
      - Check against redundancy patterns
      - Calculate redundancy percentage

   f. **Optimize if needed** (inline - no nested subagent):
      - If redundancy >10%:
          - Apply optimization fixes
          - Preserve unique content
          - Overwrite file with optimized version
          - **Recompute hash**: Invoke `analyze-local-changes compute [target_path]`
          - Count new line count
          - Report: `✅ Optimized [filename]: X → Y lines (-Z%) [hash: def456]`
      - If redundancy ≤10%:
          - Keep original
          - Report: `✅ [filename] already optimal`

   g. **Report**: `✓ [filename] regenerated`

3. **Update generation plan** (after all batches):
   - Collect all regenerated file paths
   - Invoke `analyze-local-changes update-plan <all file paths> --plugin-root ${CLAUDE_PLUGIN_ROOT}`
   - Script automatically marks `[x]`, computes Hash, looks up Source Hash from `source-hashes.json`, sets Lines

4. **Report progress**:
   ```
   Batch 1/1 complete:
   ✓ code-review-workflow.md regenerated (63 lines)
   ✓ testing-workflow.md regenerated (72 lines, 3 local changes merged)

   Regeneration complete! 2/2 files updated.

   Merged local changes:
   - testing-workflow.md: Added "Project-Specific" section
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
   ```

2. **Create generation commits** (if git is available):
   - Invoke `analyze-local-changes commit-generation --plugin-version X.Y.Z [--clean-dir /tmp/memento-clean/]`
   - Script creates base commit (clean), merge commit (if merge applied), updates Metadata
   - Report: `✅ Generation commits: base=<base>, commit=<commit>`
   - **If git not available**: Skip, warn about limited merge support for future updates.

3. **Verify merge results** (only if merge was applied):
   - For each file that was merged, check the merge stats returned by `analyze-local-changes merge`:
     - If file had local changes but merge stats show `user_added: 0` and `from_local: 0`:
       - WARNING: Local changes may not have been preserved in [filename]
       - Ask user: "Merge stats show no local content was included. Investigate?"
     - If `user_added > 0` or `from_local > 0`: local changes were incorporated
   - Report: `✅ Merge results verified: N files with local changes preserved`

4. **Validate generated content** (MANDATORY):
   - Run command: `/memento:fix-broken-links`
   - Report results

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

### Smart Detection (Auto Mode)

```
Developer: We added Playwright for E2E testing and updated Django.

/update-environment auto

AI: Analyzing current project state...

Tech Stack Changes Detected:
- Playwright added (E2E testing framework)
- Django 4.2 → 5.1 (version bump)
- PostgreSQL 15 → 16 (version bump)

Affected files:
- testing.md (NEW: Playwright patterns)
- testing-workflow.md (NEW: E2E testing workflow)
- backend.md (UPDATED: Django 5.1 features)

Plugin Updates Detected:
- research-analyst.md (NEW agent available)

Recommendations:
A: Update 3 affected files
B: Add 1 new agent
C: Both (4 files total)
D: Full regeneration

Developer: C

AI: ✓ Updated project-analysis.json
✓ Added research-analyst.md to generation plan
Regenerating 4 files...
✓ Complete
```

### Checking for Plugin Updates

```
Developer: Did the plugin get any new features?

/update-environment detect

AI: Checking for updates...

Plugin Updates Detected:
2 new agent prompts available:
- research-analyst.md (research and documentation analysis)
- security-reviewer.md (security vulnerability scanning)

Missing Static Files:
1 static file missing from project:
- development-workflow.md (MANDATORY workflow for all dev tasks)

Tech Stack: No changes detected

Recommendations:
A: Add 2 new agents only
B: Copy missing static files only (1 file)
C: Both agents + static files (3 files)
D: Skip updates

Developer: C

AI: 📋 Copied development-workflow.md (static)
Generating research-analyst.md...
✓ research-analyst.md generated
Generating security-reviewer.md...
✓ security-reviewer.md generated
✓ Complete - 3 files added
```

### After Tech Stack Migration

```
Developer: We migrated from Django to FastAPI. Update everything.

/update-environment auto

AI: Analyzing project...

CRITICAL: Major framework change detected!
- Backend: Django → FastAPI (HIGH IMPACT)
- Database: PostgreSQL (unchanged)
- Frontend: React (unchanged)

All backend-related files need regeneration:
- backend.md
- api-design.md
- testing.md
- All workflow files

Recommendation: Full regeneration recommended
→ /update-environment all

Proceed with full regeneration? Reply 'Yes'

Developer: Yes

AI: [Regenerates all files with FastAPI context]
```

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

### Preserving Local Modifications

```
Developer: We need to update the testing guide but I added project-specific sections.

/update-environment testing.md

AI: Analyzing testing.md...

⚠️ Local modifications detected:
- Hash mismatch: a1b2c3d4 → x9y8z7w6
- File was modified since last generation

Extracting local changes...
Found 2 local additions:
1. Section "### Integration Tests" (15 lines)
2. Lines added to "## Running Tests" (3 lines)

Proceed with regeneration? Local changes will be merged automatically.

Developer: Yes

AI: 📝 Regenerating testing.md...
   Applying merge strategy...
   ✓ Inserted "### Integration Tests" after "## Unit Tests"
   ✓ Appended 3 lines to "## Running Tests"

✓ testing.md regenerated (295 lines, 2 local changes merged)
```

### Cleaning Up Obsolete Files

```
Developer: The plugin was updated. Check for changes.

/update-environment detect

AI: Scanning for updates...

Obsolete Files Detected:
2 files in Memory Bank have no matching plugin prompt:
- feature-workflow.md (workflows/) - REMOVED from plugin
- current_tasks.md (.memory_bank/) - REMOVED from plugin

New Plugin Prompts:
1 new agent available:
- design-reviewer.md (agents/)

Recommendations:
A: Delete obsolete files (2 files)
B: Add new agent (1 file)
C: Both (delete 2 + add 1)
D: Skip

Developer: C

AI: 🗑️ Deleted feature-workflow.md (obsolete)
🗑️ Deleted current_tasks.md (obsolete)
✓ Removed from generation-plan.md

📝 Generating design-reviewer.md...
✓ design-reviewer.md generated (85 lines)

Complete! Deleted 2 obsolete files, added 1 new file.
```

### Handling Merge Conflicts

```
Developer: Update backend guide.

/update-environment backend.md

AI: ⚠️ Local modifications detected in backend.md

Extracting local changes...
Found 3 local additions:
1. Section "### PostgreSQL Configuration" (8 lines) ✓
2. Modified "## API Patterns" section ⚠️ CONFLICT
3. Lines added to "## Error Handling" (2 lines) ✓

Conflict detected in "## API Patterns":
- Local version has different content than plugin template
- Cannot auto-merge

Options:
A: Keep local version of conflicting section
B: Use plugin version (discard local changes in that section)
C: Show diff and decide manually
D: Skip this file entirely

Developer: C

AI: Diff for "## API Patterns":

--- Local version
+++ Plugin version
@@ -1,5 +1,4 @@
 ## API Patterns
-
-Use FastAPI patterns for all endpoints.  ← LOCAL
+Use Next.js API route patterns.  ← PLUGIN
 Always validate input with Zod schemas.

Keep local (L) or use plugin (P)?

Developer: L

AI: ✓ Keeping local version of "## API Patterns"
✓ backend.md regenerated (462 lines, 3 local changes merged)
```

## Safety Checks

Before regeneration:

1. ✓ Verify `.memory_bank/project-analysis.json` exists
2. ✓ Verify `.memory_bank/generation-plan.md` exists
3. ✓ Confirm files match filter criteria
4. ✓ Check for local modifications (hash comparison)
5. ✓ Extract local changes before regeneration
6. ✓ Show preview of files to be overwritten (with local changes indicator)
7. ✓ Wait for explicit user confirmation

After regeneration:

1. ✓ Merge local changes into regenerated content
2. ✓ Handle merge conflicts (ask user if needed)
3. ✓ Compute new hash: `md5 -q <file>`
4. ✓ Update generation plan with `[x]` marks and new hash
5. ✓ Report file sizes, line counts, and merged changes
6. ✓ Offer link validation
7. ✓ Suggest testing with AI agents

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
- `/memento:optimize-memory-bank` - Analyze and remove redundancy
- `/memento:fix-broken-links` - Find and fix broken links

## Generation Plan Format

The `generation-plan.md` file tracks all generated files with their hashes:

```markdown
## Metadata

Generation Base: a1b2c3d
Generation Commit: e4f5g6h
Generated: 2026-02-20T14:30:00
Plugin Version: 1.3.0

## Core Documentation

| Status | File | Location | Lines | Hash | Source Hash |
|--------|------|----------|-------|------|-------------|
| [x] | README.md | .memory_bank/ | 127 | a1b2c3d4 | aaa111 |
| [x] | product_brief.md | .memory_bank/ | 102 | e5f6g7h8 | bbb222 |
| [x] | tech_stack.md | .memory_bank/ | 429 | i9j0k1l2 | ccc333 |

## Guides

| Status | File | Location | Lines | Hash | Source Hash |
|--------|------|----------|-------|------|-------------|
| [x] | testing.md | .memory_bank/guides/ | 280 | m3n4o5p6 | ddd444 |
| [x] | backend.md | .memory_bank/guides/ | 450 | q7r8s9t0 | eee555 |
```

**Metadata purpose:**
- **Generation Base**: Git commit hash of clean plugin output (before user merge) — used as base for 3-way merge to correctly preserve ALL user additions across repeated updates
- **Generation Commit**: Git commit hash of final state (after user merge) — if no merge, same as Base
- **Generated**: Timestamp of last generation
- **Plugin Version**: Plugin version used for generation

**Hash columns purpose:**
- **Hash**: MD5 of generated file — quick detection of local modifications (no git needed)
- **Source Hash**: MD5 of source prompt/static — quick detection of plugin updates

**When Hash mismatches (local changes):**
1. File was modified locally since last generation
2. Base recovered via: `git show <generation_base>:<file_path>` (clean plugin output)
3. `diff(base, local)` = ALL user additions → preserved during merge

**When Source Hash mismatches (plugin updates):**
1. Source prompt/static was updated in the plugin
2. File should be regenerated/updated
3. `diff(base, new)` = plugin's changes → applied during merge
4. User's changes preserved via 3-way merge

## Implementation Notes

### Auto Mode (Step 0)

1. **Project re-analysis**: Invoke `detect-tech-stack` skill (see `.claude-plugin/skills/detect-tech-stack/`)
2. **Comparison logic**:
   - Framework change = HIGH impact (suggest regenerate all related files)
   - Major version = MEDIUM impact (suggest review and regenerate)
   - Minor version = LOW impact (optional update)
   - New library/framework = MEDIUM impact (regenerate affected files)
   - Use "Affected Files Mapping" section from spec to determine which files to update
3. **Plugin scanning**:
   - Check `${CLAUDE_PLUGIN_ROOT}/prompts/**/*.prompt` for new files
   - Compare frontmatter `target_path` and `file` with generation-plan.md
   - Evaluate `conditional` against current project-analysis.json
4. **Obsolete file detection**:
   - Scan all `.md` files in `.memory_bank/`
   - Check if corresponding prompt exists in plugin
   - Mark as obsolete if no prompt found
   - Suggest deletion (with user confirmation)
5. **Smart recommendations**: Present options with clear explanations
6. **Backup project-analysis.json**: Always backup before updating
7. **Update generation plan**: Append new files, remove obsolete files

### Hash Tracking

1. **After file generation** (batched):
   - Invoke `analyze-local-changes update-plan <file1> <file2> ... --plugin-root ${CLAUDE_PLUGIN_ROOT}`
   - Script computes file hashes, looks up source hashes from pre-computed `source-hashes.json`, updates generation-plan.md
2. **On update-environment**:
   - Invoke `analyze-local-changes detect` → compares file Hash (local modifications)
   - Invoke `analyze-local-changes detect-source-changes` → compares Source Hash (plugin updates, reads from `source-hashes.json`)
3. **Hash mismatch = local modifications**: Trigger merge strategy
4. **Source Hash mismatch = plugin updates**: Trigger regeneration

### Merge Strategy

Applies to **both** prompt-generated and static files. The only difference is how the "new version" is obtained:
- **Prompt-generated**: New version is regenerated from prompt by LLM
- **Static**: New version is read from `${CLAUDE_PLUGIN_ROOT}/static/[source]`

**Decision matrix** (determines action BEFORE merge):

| Local modified? | Source updated? | Action |
|---|---|---|
| No | No | Skip (up to date) |
| No | Yes | Safe overwrite (no merge needed) |
| Yes | No | Keep local (no plugin update) |
| Yes | Yes | 3-way merge via `analyze-local-changes merge` |

**3-way merge** is handled by the `merge` command in the `analyze-local-changes` skill:

```bash
python analyze.py merge <target> --base-commit <generation_base> --new-file <new_version>
```

The script recovers clean base via `git show`, performs section-level merge, outputs merged content + conflicts. See `analyze-local-changes/SKILL.md` Mode 6 for merge rules and output format.

**Generation Base vs Generation Commit**: The merge uses Generation Base (clean plugin output before user merge), not Generation Commit (which may contain previously-merged user additions). This prevents user additions from being silently dropped on repeated updates.

**Fallback (no Generation Base):**

- **If only Generation Commit exists** (old format): merge command falls back to it, but previously-merged user additions may be lost. Warn user.
- **If neither exists** (non-git): Offer Overwrite / Keep local / Skip — no auto-merge available.

### Manual Mode (Steps 1-5)

1. **Batch processing**: Process 5 files at a time
2. **Use existing project analysis**: Don't re-analyze unless in auto mode
3. **Check local modifications**: Hash comparison before regeneration
4. **Extract and merge local changes**: Apply merge strategy
5. **Update generation plan**: Mark files as completed, update hash
6. **Parse filter flexibly**: Handle typos, case-insensitive matching
7. **Show preview**: Clear preview before any overwrites (with local changes indicator)
8. **Report progress**: Update during batch generation
9. **Offer follow-up**: Validation, testing options after completion

### When to Use Auto Mode

- After installing new dependencies (npm install, pip install)
- After upgrading frameworks (React 17→18, Django 4→5)
- After adding new testing frameworks (adding Playwright, Cypress)
- After migrating tech stack (Django→FastAPI, Vue→React)
- After plugin updates (new agents/commands available)
- Periodically (monthly) to keep documentation in sync

### When to Use Manual Mode

- Fixing specific documentation issues
- Updating after changing single file template
- Regenerating category after workflow changes
- Testing documentation improvements
- Quick updates without full analysis
