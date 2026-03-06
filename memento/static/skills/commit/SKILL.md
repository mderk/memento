---
name: commit
description: Stage changes and create a git commit with a well-formatted message. Use when the user asks to commit, or when a workflow requires committing changes.
version: 1.1.0
---

# Git Commit Skill

Stage changes and commit with a message that follows project conventions.

## When to Use

-   User explicitly asks to commit (`/commit`)
-   Workflow step requires committing

## CRITICAL: Bash Execution Rules

Every `git` invocation MUST be its own **separate Bash tool call**.

-   **NEVER** chain commands: ~~`git diff --stat && git status -s`~~
-   **NEVER** prefix with cd: ~~`cd /path && git add .`~~
-   **NEVER** use `-C` flag: ~~`git -C /path add .`~~
-   **DO** launch independent git calls **in parallel** (multiple Bash tool calls in one message).

Why: Claude Code matches each Bash call against allow-list patterns like `Bash(git diff*)`. Chained or prefixed commands don't match and trigger a permission prompt.

## Process

### Step 1: Read Rules

Read `.memory_bank/workflows/commit-message-rules.md` for the commit message conventions.

### Step 2: Analyze Changes

Run **3 parallel** Bash calls:

-   `git status -s`
-   `git diff --stat`
-   `git diff --cached --stat`

If nothing is staged, stage relevant files. Prefer `git add <specific files>` over `git add -A`. Never stage `.env`, credentials, or large binaries.

### Step 3: Understand the Diff

```
git diff --cached
```

Read the actual diff. Identify:

-   The **main theme** of the changes
-   Whether there are minor unrelated tweaks alongside

### Step 4: Compose Message and Commit

Apply the rules from Step 1. Then commit:

```
git commit -m "<message>"
```

If the message needs a body (rare), use a heredoc:

```
git commit -m "$(cat <<'EOF'
subject line

body line
EOF
)"
```

### Step 5: Verify

```
git log -1 --oneline
```
