---
description: Update Memory Bank files after tech stack changes or plugin updates with smart detection
---

# Update Environment Files

This command allows selective update/regeneration of Memory Bank files. It can:

1. **Detect tech stack changes** - Compare current project state with initial analysis
2. **Find plugin updates** - Discover new prompts/agents added to the plugin
3. **Smart recommendations** - Suggest which files need updating based on detected changes
4. **Manual selection** - Update specific files, patterns, or categories

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

1. **Scan plugin prompts**:
   - Read all files in `${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/*.prompt`
   - Read all files in `${CLAUDE_PLUGIN_ROOT}/prompts/agents/*.prompt`
   - Read all files in `${CLAUDE_PLUGIN_ROOT}/prompts/commands/*.prompt`
   - Extract file names and target paths from frontmatter

2. **Load generation plan**:
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

#### 0.3: Present Recommendations

Combine findings from 0.1, 0.2 (prompts), and 0.2 (static files):

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

## 4. Suggested Actions

Option A: Update affected files only (3 files)
→ Regenerate testing.md, testing-workflow.md, backend.md

Option B: Add new prompts only (2 files)
→ Generate research-analyst.md and security-reviewer.md

Option C: Copy missing static files (1 file)
→ Copy development-workflow.md from plugin

Option D: All of the above (6 files total)
→ Update existing + add new prompts + copy static files

Option E: Full regeneration (all files)
→ /update-environment all

Which option would you like? Reply with A, B, C, D, or E.
```

6. **Wait for user choice**, then proceed based on selection:
   - **Option A**: Continue to Step 1 with filter = affected files only
   - **Option B**: Continue to Step 1 with filter = new prompts only
   - **Option C**: Copy static files immediately (no LLM generation needed):
     - Read each file from `${CLAUDE_PLUGIN_ROOT}/static/[source]`
     - Write to project `[target]` (create directories if needed)
     - Report: `📋 Copied [filename] (static)`
     - Skip to Step 5 (no regeneration needed)
   - **Option D**: Copy static files FIRST, then continue to Step 1 with combined filter
   - **Option E**: Continue to Step 1 with filter = "all" (includes copying static files first)

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

### Step 4: Regenerate Files

After user confirms with "Yes" (or "Go", "Continue", "Proceed"):

1. **Process in batches**: Use Task tool to regenerate 5 files at a time

2. **For each file in batch**:

   a. **Find and read prompt template**:
      - Determine prompt path based on file type:
        - Memory Bank files: `${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/{filename}.prompt`
        - Agents: `${CLAUDE_PLUGIN_ROOT}/prompts/agents/{filename}.prompt`
        - Commands: `${CLAUDE_PLUGIN_ROOT}/prompts/commands/{filename}.prompt`
      - Example: `README.md` → `${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/README.md.prompt`
      - Read the prompt file completely
      - Report: `📝 Regenerating [filename]...`

   b. **Generate content following prompt instructions**:
      - Read `.memory_bank/project-analysis.json` for input data
      - The prompt contains detailed generation instructions, examples, and quality checklist
      - Follow the prompt's "Output Requirements" section exactly
      - Apply conditional logic from prompt based on project-analysis.json
      - Use project-specific values from project-analysis.json (no placeholders)
      - Ensure output matches prompt's structure and length requirements
      - Validate against prompt's "Quality Checklist" before writing

   c. **Write generated file**: Overwrite target file with new content

   d. **Report**: `✓ [filename] regenerated (X lines)`

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
4. **Smart recommendations**: Present A/B/C/D options with clear explanations
5. **Backup project-analysis.json**: Always backup before updating
6. **Update generation plan**: Append new files with appropriate priority

### Manual Mode (Steps 1-5)

1. **Batch processing**: Process 5 files at a time
2. **Use existing project analysis**: Don't re-analyze unless in auto mode
3. **Update generation plan**: Mark files as completed after regeneration
4. **Preserve manual edits**: Warn if files have manual edits (check git status)
5. **Parse filter flexibly**: Handle typos, case-insensitive matching
6. **Show preview**: Clear preview before any overwrites
7. **Report progress**: Update during batch generation
8. **Offer follow-up**: Validation, testing options after completion

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
