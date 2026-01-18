---
description: Update Memory Bank files after tech stack changes or plugin updates with smart detection
---

# Update Environment Files

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
   - Read all files in `${CLAUDE_PLUGIN_ROOT}/prompts/agents/*.prompt`
   - Read all files in `${CLAUDE_PLUGIN_ROOT}/prompts/commands/*.prompt`
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
   - For each file in manifest:
     - Check if target file exists in project directory
     - If missing → mark as "NEW static file"
     - If exists → compare content (optional: check if plugin version is newer)
   - Build list of static files to add/update:
     ```markdown
     ## Static Files Updates

     Found 1 new static file:
     - development-workflow.md (workflows/) - MANDATORY workflow for all dev tasks

     Found 0 updated static files.

     → Recommendation: COPY missing static files
     ```

6. **Check for obsolete files** (files in MB but removed from plugin):
   - Scan all files in `.memory_bank/` directory
   - For each file, check if corresponding prompt exists in plugin:
     - Memory Bank files: `${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/{filename}.prompt`
     - Agents: `${CLAUDE_PLUGIN_ROOT}/prompts/agents/{filename}.prompt`
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

1. **Invoke `analyze-local-changes` skill** with `detect` command

2. **Parse skill output**:
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

3. **For each modified file, analyze changes**:
   - Invoke `analyze-local-changes` skill with `analyze <file>`

4. **Build local modifications report**:
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

Option C: Copy missing static files (1 file)
→ Copy development-workflow.md from plugin

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
   - **Option C**: Copy static files immediately (no LLM generation needed):
     - Read each file from `${CLAUDE_PLUGIN_ROOT}/static/[source]`
     - Write to project `[target]` (create directories if needed)
     - Report: `📋 Copied [filename] (static)`
     - Skip to Step 5 (no regeneration needed)
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

4. **Show preview to user**:
   ```
   Found 2 files matching criteria "workflows":

   1. code-review-workflow.md (workflows/)
   2. testing-workflow.md (workflows/)

   These files will be OVERWRITTEN. Proceed? Reply 'Yes' to continue.
   ```

5. **Wait for user confirmation** before proceeding

### Step 4: Regenerate Files (with Merge Strategy)

After user confirms with "Yes" (or "Go", "Continue", "Proceed"):

1. **Process in batches**: Use Task tool to regenerate 5 files at a time

2. **For each file in batch**:

   a. **Check for local modifications** (if hash mismatch detected in Step 0.2.5):
      - If file has local modifications, invoke `analyze-local-changes` skill with `analyze <file> --base <temp_base_file>`
      - Skill returns structured analysis:
        ```json
        {
          "changes": [
            {"type": "new_section", "header": "### Project-Specific Tests", ...},
            {"type": "added_lines", "in_section": "## Running Tests", ...}
          ],
          "merge_strategy": {
            "auto_mergeable": [...],
            "requires_review": [...]
          }
        }
        ```
      - Store changes and merge strategy for merge step

   b. **Find and read prompt template**:
      - Determine prompt path based on file type:
        - Memory Bank files: `${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/{filename}.prompt`
        - Agents: `${CLAUDE_PLUGIN_ROOT}/prompts/agents/{filename}.prompt`
        - Commands: `${CLAUDE_PLUGIN_ROOT}/prompts/commands/{filename}.prompt`
      - Example: `README.md` → `${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/README.md.prompt`
      - **Compute source hash**: Invoke `analyze-local-changes` skill with `compute-source [prompt_path] --plugin-root ${CLAUDE_PLUGIN_ROOT}`
      - Read the prompt file completely
      - Report: `📝 Regenerating [filename]...`

   c. **Generate content following prompt instructions**:
      - Read `.memory_bank/project-analysis.json` for input data
      - The prompt contains detailed generation instructions, examples, and quality checklist
      - Follow the prompt's "Output Requirements" section exactly
      - Apply conditional logic from prompt based on project-analysis.json
      - Use project-specific values from project-analysis.json (no placeholders)
      - Ensure output matches prompt's structure and length requirements
      - Validate against prompt's "Quality Checklist" before writing

   d. **Merge local changes** (if extracted in step a):
      - For each extracted local change:
        - **Added section**: Append to end of file or insert after matching parent section
        - **Added lines in existing section**: Find section by header, append lines
        - **Modified content**: Show conflict, ask user to resolve
      - Example merge:
        ```markdown
        ## Local Changes Merged into testing.md:

        ✓ Added section "### Integration Tests" (after "## Unit Tests")
        ✓ Added 3 lines to "## Running Tests" section
        ⚠️ Conflict in "## Test Commands" - manual review needed
        ```

   e. **Write generated file**: Write merged content to target file

   f. **Compute and store hashes**:
      - Invoke `analyze-local-changes` skill with `compute [target_path]`
      - Extract file hash from output
      - Update generation-plan.md with:
        - New file Hash (from compute)
        - New Source Hash (from step b)

   g. **Report**: `✓ [filename] regenerated (X lines, Y local changes merged) [hash: abc123, source: def456]`

3. **Update generation plan**:
   - Mark regenerated files as `[x]` in `.memory_bank/generation-plan.md`
   - Update Hash column with new file hash
   - Update Source Hash column with new source hash
   - Update line count

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
- `/optimize-memory-bank` - Analyze and remove redundancy
- `/fix-broken-links` - Find and fix broken links
- `/validate-links` - Validate all internal links

## Generation Plan Format

The `generation-plan.md` file tracks all generated files with their hashes:

```markdown
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

**Hash columns purpose:**
- **Hash**: MD5 of generated file - detects local modifications
- **Source Hash**: MD5 of source prompt/static - detects plugin updates

**When Hash mismatches (local changes):**
1. File was modified locally since last generation
2. Local changes will be extracted and merged during regeneration
3. User can choose to skip files with local changes

**When Source Hash mismatches (plugin updates):**
1. Source prompt/static was updated in the plugin
2. File should be regenerated to get new content
3. Local changes (if any) will be preserved via merge

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

1. **After each file generation**:
   - Compute file hash: Invoke `analyze-local-changes compute <file>`
   - Compute source hash: Invoke `analyze-local-changes compute-source <prompt> --plugin-root ${CLAUDE_PLUGIN_ROOT}`
2. **Store in generation-plan.md**: Update both Hash and Source Hash columns
3. **On update-environment**:
   - Invoke `analyze-local-changes detect` → compares file Hash (local modifications)
   - Invoke `analyze-local-changes detect-source-changes` → compares Source Hash (plugin updates)
4. **Hash mismatch = local modifications**: Trigger merge strategy
5. **Source Hash mismatch = plugin updates**: Trigger regeneration

### Merge Strategy

1. **Detect local changes**:
   - Compare current hash with stored hash
   - If mismatch → file was modified locally

2. **Extract local additions** (before regeneration):
   - Use git diff if available: `git diff HEAD -- <file>`
   - Or compare with freshly regenerated temp file
   - Parse diff to identify: added sections, added lines, modified content

3. **Classify changes**:
   - **New section** (new `##` or `###` header): Safe to auto-merge
   - **Added lines** in existing section: Safe to append
   - **Modified content**: Potential conflict, ask user

4. **Apply merge** (after regeneration):
   - Insert new sections at appropriate locations
   - Append added lines to matching sections
   - For conflicts: show diff, let user choose

5. **Update hashes**: Compute and store both hashes after merge:
   - New file Hash (from regenerated content)
   - New Source Hash (from prompt used for regeneration)

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
