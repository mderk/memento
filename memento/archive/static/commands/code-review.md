---
description: Run specialized code review with parallel competency checks
---

# Rule: Code Review

Orchestrate a multi-competency code review by spawning parallel sub-agents.

## Step 1: Determine Scope

```bash
# Default: uncommitted changes
git diff --name-only
git diff --cached --name-only

# If argument provided: specific files, branch, or PR
# e.g., /code-review main..HEAD
# e.g., /code-review src/auth/
```

Collect the list of changed files.

## Step 2: Select Competencies

Read `.memory_bank/workflows/code-review-workflow.md` → **Review Competencies** section.

Select competencies based on the changed files using the competency selection guide and the auto-detection table below:

| File pattern | Competencies |
|---|---|
| `*.py` | architecture, security, performance, simplicity, **python** |
| `*.ts`, `*.tsx` | architecture, security, performance, simplicity, **typescript** |
| `*migration*`, `*schema*`, `*.sql` | **data-integrity**, performance |
| `*auth*`, `*login*`, `*token*`, `*secret*` | **security**, architecture |
| `*test*`, `*spec*`, `*_test.*`, `*.test.*` | **testing** (if review/testing.md exists) |
| Any other code | architecture, simplicity |
| Config/docs only | security (secrets scan only) |

Always include **simplicity**. When unsure, include all universal competencies.

## Step 3: Spawn Parallel Reviews

For each selected competency, launch a Task sub-agent in parallel:

```
Task(subagent_type="general-purpose", prompt="""
You are a code reviewer specializing in {COMPETENCY_NAME}.

1. Read the review rules: `.memory_bank/workflows/review/{COMPETENCY_FILE}`
2. Run `git diff` to see the actual changes being reviewed
3. Review ONLY the changes in the diff against those rules. Use surrounding code for context, but findings must be grounded in the current change.
4. If you spot a pre-existing issue in unchanged code that is CRITICAL or REQUIRED, flag it separately as [PRE-EXISTING].
5. Report findings using the output format from `.memory_bank/workflows/code-review-workflow.md`

Changed files: {FILE_LIST}

Do NOT modify any files. Only review and report.
""")
```

## Step 4: Synthesize Results

Combine all sub-agent findings into one report. Follow the synthesized report format from `.memory_bank/workflows/code-review-workflow.md` → Output Format.

**Triage every CRITICAL/REQUIRED finding** using the triage table from `.memory_bank/workflows/code-review-workflow.md` → Finding Triage. Each finding gets an explicit FIX / DEFER / ACCEPT verdict with rationale. Never batch-dismiss.
