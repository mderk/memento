---
description: Generate a comprehensive AI-friendly development environment for your project
---

# Create AI-Friendly Development Environment

## Phase 0: Check Existing Files

1. Check if `.memory_bank/project-analysis.json` and `.memory_bank/generation-plan.md` exist

2. **If both files exist**:

    - Ask user: "Found existing generation plan. Use existing plan (resume) or Regenerate (start fresh)?"
    - If "Use existing plan": Skip to Phase 2
    - If "Regenerate": Delete old files, continue to Phase 1

3. **If incomplete or missing**: Delete incomplete files, continue to Phase 1

## Phase 1: Create Generation Plan

1. **Launch planning agent**: Use the Task tool with `subagent_type="general-purpose"` to create the generation plan.

2. **Provide context**: In your prompt to the agent, include:

    - Task: Analyze project structure and create generation plan
    - Steps to perform:
        - **Detect project tech stack**: Invoke `detect-tech-stack` skill
          - Skill will scan dependency files and output JSON with detected technologies
          - Save skill output to `.memory_bank/project-analysis.json`
        - **Scan static files**: Read `${CLAUDE_PLUGIN_ROOT}/static/manifest.yaml`
          - These are universal files copied without LLM generation
          - Evaluate conditionals against project-analysis.json
          - Include applicable static files in generation plan (priority 0 = first)
        - Analyze available templates in ALL prompt directories:
            - `${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/` → generates to `.memory_bank/`
            - `${CLAUDE_PLUGIN_ROOT}/prompts/agents/` → generates to `.claude/agents/`
            - `${CLAUDE_PLUGIN_ROOT}/prompts/commands/` → generates to `.claude/commands/`
        - Evaluate which templates are relevant to detected project stack
        - Create `.memory_bank/project-analysis.json` with all detected data
        - Create `.memory_bank/generation-plan.md` with:
            - Project analysis summary
            - **Static files section (Priority 0)**: Files from manifest.yaml to copy
            - Files grouped by priority (1-10, 11-20, etc.)
            - Each file with `[ ]` checkbox, name, target path, priority
            - Include Memory Bank files, agents, and commands
            - Skipped files section with reasons
    - Output: Ask user "Generation plan created. Review `.memory_bank/generation-plan.md`. Ready to generate? Reply with **Go** to proceed."

3. **Wait for user confirmation** ("Go") before Phase 2

## Phase 2: Generate Files

After user confirms with "Go":

1. **Read generation plan**: Get list of files from `.memory_bank/generation-plan.md`

2. **Copy static files FIRST** (MANDATORY - do this before any LLM generation):

    - Read `${CLAUDE_PLUGIN_ROOT}/static/manifest.yaml`
    - Read `.memory_bank/project-analysis.json` for conditional evaluation
    - For each file in manifest:
        - Evaluate `conditional` against project-analysis.json
        - If conditional is `null` or evaluates to `true`:
            - Read file from `${CLAUDE_PLUGIN_ROOT}/static/[source]`
            - Write to project `[target]` (create directories if needed)
            - Report: `📋 Copied [filename] (static)`
        - If conditional evaluates to `false`:
            - Report: `⏭️ Skipped [filename] (condition not met)`
    - Summary: `✓ Static files: X copied, Y skipped`

    **Example for development-workflow.md:**
    ```
    Source: ${CLAUDE_PLUGIN_ROOT}/static/memory_bank/workflows/development-workflow.md
    Target: .memory_bank/workflows/development-workflow.md
    ```

3. **Check progress**: Look for `[x]` marks, report if resuming

4. **Group files into batches**:

    - Batch size: **5 files per batch** (recommended)
    - Group uncompleted files by priority ranges (e.g., files 1-5, 6-10, 11-15)
    - Prepare batch list with file paths and priorities

5. **Launch batch agents** (parallel processing):

    - Use Task tool with `subagent_type="general-purpose"` for EACH batch
    - Launch multiple batch Tasks in **single message** for parallel execution
    - Example: 35 files = 7 batches → send 7 Task calls in one message

6. **For EACH batch** (agent instructions):

    a. **Load generation context ONCE** (reuse for all 5 files in batch):

    - Read `.memory_bank/project-analysis.json`
    - Load documentation quality standards
    - Load project-specific templates and patterns

    b. **For EACH file in batch** (sequential within batch):

    i. **Read template**: Read documentation template from generation-plan.md
       - Extract target path and conditional requirements
       - Check conditional - skip if condition not met
       - Report: `📝 Generating [filename]...`

    ii. **Generate content**:
        - Apply conditional logic based on project-analysis.json
        - Use project-specific values (no placeholders)
        - Apply quality standards and anti-redundancy rules
        - Generate in English, professional tone
        - Ensure completeness (no TODOs or TBDs)

    iii. **Write generated file**: Write content to target path

    iv. **Check redundancy** (MANDATORY, inline - no nested subagent):
        - Report: `🔍 Checking [filename] for redundancy...`
        - Count lines in generated file
        - Check against redundancy patterns
        - Calculate redundancy percentage

    v. **Optimize if needed** (inline - no nested subagent):
       - If redundancy >10%:
           - Apply optimization fixes
           - Preserve unique content
           - Overwrite file with optimized version
           - Count new line count
           - Report: `✅ Optimized [filename]: X → Y lines (-Z%)`
       - If redundancy ≤10%:
           - Keep original
           - Report: `✅ [filename] already optimal`

    vi. **Track progress**: Add completed file to batch summary

    c. **Batch completion report** (return to main assistant):

    - Return list of completed files in batch: `[file1.md, file2.md, file3.md, file4.md, file5.md]`
    - Return optimization stats: `3 optimized (avg -32%), 2 already optimal`
    - Report: `✓ Batch 1-5 complete: 5 files generated, 3 optimized (avg -32%), 2 already optimal`

7. **Update progress** (main assistant, after batches complete):

    - Wait for ALL batch agents to complete
    - For EACH completed batch:
        - Edit `.memory_bank/generation-plan.md`: change `[ ]` to `[x]` for all files reported by batch
    - Report overall progress: `✓ Phase 2 complete: 35/35 files generated`

8. **Proceed to validation**: Continue to Phase 3

## Phase 3: Validate Generated Content

After all files are generated, validate the integrity of the generated environment:

1. **Validate UTF-8 encoding and fix links**:

    - Run command: `/fix-broken-links`
    - Command will:
      - **Validate UTF-8 encoding** (fails if any file has encoding issues)
      - Scan Memory Bank files for broken links
      - If broken links found: automatically fix them (update or remove)
      - Re-validate to confirm fixes
      - Report results
    - **If encoding error found**: File was corrupted or edited with wrong encoding
      - Regenerate file OR manually fix encoding (save as UTF-8)
    - If command reports other issues: Review and address manually

2. **Check redundancy** (inline, no subagent):

    - Read generation-plan.md to get target line counts (if specified in prompts)
    - For each generated file:
        - Count actual lines: `wc -l <file>`
        - Compare to target (if exists)
        - Flag if actual > target * 1.2 (20% over)
    - Report: "⚠️ X files exceed target by Y% average" or "✅ All files within target size"

3. **Verify directory structure**:

    - Check directories exist: `.memory_bank/`, `.memory_bank/guides/`, `.memory_bank/workflows/`, `.memory_bank/patterns/`
    - Check directories exist: `.claude/agents/`, `.claude/commands/`
    - Report: "✅ Directory structure complete" or list missing directories

4. **Final summary**:

    - Report total files generated
    - Report validation script results
    - Report redundancy check results
    - If any issues found: List specific problems
    - If all passed: "✅ Environment validated successfully"
    - Direct user to `.memory_bank/generation-plan.md` for review
    - Recommend: "Run `/prime` to load Memory Bank context"
    - If redundancy found: Suggest: "Run `/optimize-memory-bank` to reduce verbosity"

## Troubleshooting

**Phase 1 fails**: Ensure project has package.json or requirements.txt

**Phase 2 fails**: Check generation-plan.md for `[x]` marks. Can resume by running command again.

**Phase 3 validation errors**:

-   Missing files: Check which files failed generation, run command again to regenerate them
-   Broken links: Review index.md files, ensure referenced files exist in plan
-   Invalid cross-references: Check if conditional files were skipped but still referenced
