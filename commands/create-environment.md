---
description: Generate a comprehensive AI-friendly development environment for your project
---

# Create AI-Friendly Development Environment

> **Note: File Access Permissions**
>
> During generation, Claude Code will request permission to read plugin files (prompts, templates, manifests). This is expected - plugins don't have automatic read access to their own directories. You can:
>
> -   Approve each request as it appears
> -   Add `Read(~/.claude/plugins/**)` to your `.claude/settings.json` to avoid repeated prompts
>
> See [README - File Access Permissions](https://github.com/mderk/memento#file-access-permissions) for details.

## Phase 0: Check Existing Files

1. Check if `.memory_bank/project-analysis.json` and `.memory_bank/generation-plan.md` exist

2. **If both files exist**:

    - **Detect local modifications**: Invoke `analyze-local-changes` skill with `detect` command
    - If modified files found, report:

        ```
        Found existing environment with local modifications:
        ⚠️ 3 files modified since last generation:
          - .memory_bank/guides/testing.md
          - .memory_bank/workflows/bug-fixing.md
          - .claude/commands/prime.md

        Options:
        A: Resume — continue from last checkpoint (skips completed files)
        B: Regenerate with merge — recreate all files, preserve local changes
        C: Regenerate fresh — overwrite everything (local changes will be lost!)
        ```

    - If no modified files: Ask "Resume or Regenerate?"
    - **Option A (Resume)**: Skip to Phase 2
    - **Option B (Regenerate with merge)**:
        - Read `Generation Base` from generation-plan.md Metadata section (fall back to `Generation Commit` if no Base)
        - Store base commit hash — Phase 2 will use `analyze-local-changes merge` per file (handles base recovery automatically)
        - Continue to Phase 1 (re-plan), then Phase 2 applies merge after each file write
        - **If no Generation Base/Commit** (old format): warn user that 3-way merge is unavailable, offer overwrite or skip per file
    - **Option C (Regenerate fresh)**: Delete old files, continue to Phase 1 (no merge)

3. **If incomplete or missing**: Delete incomplete files, continue to Phase 1

## Phase 1: Create Generation Plan

1. **Launch planning agent**: Use the Task tool with `subagent_type="general-purpose"` to create the generation plan.

2. **Provide context**: In your prompt to the agent, include:

    - Task: Analyze project structure and create generation plan
    - Steps to perform:

        - **Detect project tech stack**: Run detection and save directly:
            ```bash
            python ${CLAUDE_PLUGIN_ROOT}/skills/detect-tech-stack/scripts/detect.py --output .memory_bank/project-analysis.json
            ```
        - **Scan static files**: Read `${CLAUDE_PLUGIN_ROOT}/static/manifest.yaml`
            - These are universal files copied without LLM generation
            - Evaluate conditionals against project-analysis.json
            - Include applicable static files in generation plan (priority 0 = first)
        - Analyze available templates in ALL prompt directories:
            - `${CLAUDE_PLUGIN_ROOT}/prompts/` → root files (CLAUDE.md → `./`)
            - `${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/` → generates to `.memory_bank/`
        - Evaluate which templates are relevant to detected project stack
        - Create `.memory_bank/project-analysis.json` with all detected data
        - Create `.memory_bank/generation-plan.md` with:
            - Project analysis summary
            - **Static files section (Priority 0)**: Files from manifest.yaml to copy
            - Files grouped by priority (1-10, 11-20, etc.)
            - Table format with columns: Status, File, Location, Lines, Hash, Source Hash
            - Each file with `[ ]` checkbox, name, target path, priority
            - Hash and Source Hash columns initially empty (filled after generation)
            - Include Memory Bank files, agents, and commands
            - Skipped files section with reasons

        **Generation plan format:**

        ```markdown
        ## Metadata

        Generation Base: (pending)
        Generation Commit: (pending)
        Generated: 2026-02-20T14:30:00
        Plugin Version: 1.3.0

        ## Files

        | Status | File       | Location             | Lines | Hash | Source Hash |
        | ------ | ---------- | -------------------- | ----- | ---- | ----------- |
        | [ ]    | README.md  | .memory_bank/        | ~127  |      |             |
        | [ ]    | testing.md | .memory_bank/guides/ | ~280  |      |             |
        ```

    - Output: Ask user "Generation plan created. Review `.memory_bank/generation-plan.md`. Ready to generate? Reply with **Go** to proceed."

3. **Wait for user confirmation** ("Go") before Phase 2

## Phase 2: Generate Files

After user confirms with "Go":

1. **Read generation plan**: Get list of files from `.memory_bank/generation-plan.md`

2. **Copy static files FIRST** (MANDATORY - do this before any LLM generation):

    Run a single command to copy all applicable static files:

    ```bash
    python ${CLAUDE_PLUGIN_ROOT}/skills/analyze-local-changes/scripts/analyze.py copy-static \
      --plugin-root ${CLAUDE_PLUGIN_ROOT} \
      --clean-dir /tmp/memento-clean
    ```

    For **merge mode** (Phase 0 Option B), add `--base-commit <generation_base>`:

    ```bash
    python ${CLAUDE_PLUGIN_ROOT}/skills/analyze-local-changes/scripts/analyze.py copy-static \
      --plugin-root ${CLAUDE_PLUGIN_ROOT} \
      --clean-dir /tmp/memento-clean \
      --base-commit <generation_base>
    ```

    The script handles everything:
    - Reads manifest.yaml and evaluates conditionals against project-analysis.json
    - Copies applicable files to project targets and `/tmp/memento-clean/`
    - In merge mode: performs 3-way merge for files with local changes
    - Reports copied, merged, conflict, and skipped files in JSON

    After copy-static completes, batch update the generation plan:

    ```bash
    python ${CLAUDE_PLUGIN_ROOT}/skills/analyze-local-changes/scripts/analyze.py update-plan \
      <all copied/merged target paths> --plugin-root ${CLAUDE_PLUGIN_ROOT}
    ```

    Handle any `has_conflicts` entries from the JSON by presenting conflicts to user.

    Summary: `✓ Static files: X copied, Y skipped`

3. **Check progress**: Look for `[x]` marks, report if resuming

4. **Group files into batches**:

    - Batch size: **5 files per batch** (recommended)
    - Group uncompleted files by priority ranges (e.g., files 1-5, 6-10, 11-15)
    - Prepare batch list with file paths and priorities

5. **Launch batch agents** (parallel processing):

    - Use Task tool with `subagent_type="general-purpose"` for EACH batch
    - Launch multiple batch Tasks in **single message** for parallel execution
    - Example: 35 files = 7 batches → send 7 Task calls in one message

    **Subagent rules** (include in every Task prompt):
    - Write the file(s) only — do NOT validate output (link checking, cross-references). Validation is handled by a separate step.
    - Use built-in tools (Read, Grep, Glob) for file operations — do NOT use bash cat/grep/find/head/tail.
    - Do NOT search the codebase beyond what is provided in the prompt context.

6. **For EACH batch** (agent instructions):

    a. **Load generation context ONCE** (reuse for all 5 files in batch):

    - Read `.memory_bank/project-analysis.json`
    - Load documentation quality standards
    - Load project-specific templates and patterns

    b. **For EACH file in batch** (sequential within batch):

    i. **Find and read prompt template**:

    - Determine prompt path based on file type:
        - Root files (CLAUDE.md): `${CLAUDE_PLUGIN_ROOT}/prompts/{filename}.prompt`
        - Memory Bank files: `${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/{filename}.prompt`
    - Examples:
        - `CLAUDE.md` → `${CLAUDE_PLUGIN_ROOT}/prompts/CLAUDE.md.prompt` (root)
        - `README.md` → `${CLAUDE_PLUGIN_ROOT}/prompts/memory_bank/README.md.prompt`
    - Read the prompt file completely
    - Extract frontmatter (target_path, conditional, priority)
    - Check conditional against project-analysis.json - skip if condition not met
    - Report: `📝 Generating [filename]...`

    ii. **Generate content following prompt instructions**:

    - The prompt contains detailed generation instructions, examples, and quality checklist
    - Follow the prompt's "Output Requirements" section exactly
    - Apply conditional logic from prompt based on project-analysis.json
    - Use project-specific values from project-analysis.json (no placeholders)
    - Ensure output matches prompt's structure and length requirements
    - Validate against prompt's "Quality Checklist" before writing

    iii. **Save clean version** to `/tmp/memento-clean/[target_path]`

    iv. **Merge local changes** (if merge mode from Phase 0 Option B and file has local changes):

    - Invoke `analyze-local-changes merge [target] --base-commit <generation_base> --new-file /tmp/memento-clean/[target] --write`
    - If no conflicts: script writes merged content directly to target (no extra read/write needed)
    - If conflicts: script does NOT write, returns conflicts JSON — show to user, resolve, write manually
    - Report: `🔀 Merged N local changes into [filename]`
    - If no merge: write clean version to target

    v. **Report written file**:

    - Report: `📝 [filename] written`
    - Track target path for batch completion report

    vi. **Check redundancy** (MANDATORY, inline - no nested subagent):

    - Report: `🔍 Checking [filename] for redundancy...`
    - Count lines in generated file
    - Check against redundancy patterns
    - Calculate redundancy percentage

    vii. **Optimize if needed** (inline - no nested subagent):

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

    viii. **Track progress**: Add completed file with hash to batch summary

    c. **Batch completion report** (return to main assistant):

    - Return list of completed file paths:
        ```
        .memory_bank/guides/testing.md
        .memory_bank/guides/backend.md
        .memory_bank/guides/frontend.md
        .memory_bank/guides/architecture.md
        .memory_bank/guides/getting-started.md
        ```
    - Return optimization stats: `3 optimized (avg -32%), 2 already optimal`
    - Report: `✓ Batch 1-5 complete: 5 files generated, 3 optimized (avg -32%), 2 already optimal`

7. **Update progress** (main assistant, after batches complete):

    - Wait for ALL batch agents to complete
    - Collect all file paths from all completed batches
    - **Invoke `analyze-local-changes update-plan <all file paths> --plugin-root ${CLAUDE_PLUGIN_ROOT}`**
        - Script automatically: computes file hashes, looks up source hashes from `source-hashes.json`, updates generation-plan.md (marks `[x]`, sets Hash, Source Hash, Lines)
    - Report from returned JSON: `✓ Phase 2 complete: 35/35 files generated`

    **Updated generation-plan.md after generation:**

    ```markdown
    | Status | File       | Location             | Lines | Hash   | Source Hash |
    | ------ | ---------- | -------------------- | ----- | ------ | ----------- |
    | [x]    | README.md  | .memory_bank/        | 127   | abc123 | aaa111      |
    | [x]    | testing.md | .memory_bank/guides/ | 295   | def456 | bbb222      |
    ```

8. **Proceed to validation**: Continue to Phase 3

## Phase 3: Validate Generated Content

After all files are generated, validate the integrity of the generated environment:

1. **Validate UTF-8 encoding and fix links**:

    - Run command: `/memento:fix-broken-links`
    - Command will:
        - **Validate UTF-8 encoding** (fails if any file has encoding issues)
        - Scan Memory Bank files for broken links
        - If broken links found: automatically fix them (update or remove)
        - Re-validate to confirm fixes
        - Report results
    - **If encoding error found**: File was corrupted or edited with wrong encoding
        - Regenerate file OR manually fix encoding (save as UTF-8)
    - If command reports other issues: Review and address manually

2. **Verify merge results** (only if merge mode was used):

    - For each file that was merged in Phase 2, check the merge stats returned by `analyze-local-changes merge`:
        - If file had local changes but merge stats show `user_added: 0` and `from_local: 0`:
            - WARNING: Local changes may not have been preserved in [filename]
            - Ask user: "Merge stats show no local content was included. Investigate?"
        - If `user_added > 0` or `from_local > 0`: local changes were incorporated
    - Report: `✅ Merge results verified: N files with local changes preserved`

3. **Verify directory structure**:

    - Check directories exist: `.memory_bank/`, `.memory_bank/guides/`, `.memory_bank/workflows/`, `.memory_bank/patterns/`
    - Check directories exist: `.claude/agents/`, `.claude/commands/`
    - Report: "✅ Directory structure complete" or list missing directories

4. **Create generation commits** (if git is available):

    - Invoke `analyze-local-changes commit-generation --plugin-version X.Y.Z [--clean-dir /tmp/memento-clean/]`
    - Pass `--clean-dir` only if merge was applied (Phase 0 Option B)
    - Script creates base commit (clean plugin output), merge commit (if needed), updates Metadata
    - Report: `✅ Generation commits: base=<base>, commit=<commit>`
    - **If git not available**: Skip, leave both as `(none)`. Warn: "3-way merge unavailable for future updates — commit manually for full merge support."

5. **Final summary**:

    - Report total files generated
    - Report validation script results
    - Report redundancy check results
    - If any issues found: List specific problems
    - If all passed: "✅ Environment validated successfully"
    - Direct user to `.memory_bank/generation-plan.md` for review
    - Recommend: "Run `/prime` to load Memory Bank context"
    - If redundancy found: Suggest: "Run `/memento:optimize-memory-bank` to reduce verbosity"

## Troubleshooting

**Phase 1 fails**: Ensure project has package.json or requirements.txt

**Phase 2 fails**: Check generation-plan.md for `[x]` marks. Can resume by running command again.

**Phase 3 validation errors**:

-   Missing files: Check which files failed generation, run command again to regenerate them
-   Broken links: Review index.md files, ensure referenced files exist in plan
-   Invalid cross-references: Check if conditional files were skipped but still referenced
