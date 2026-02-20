---
name: commit
description: Stage changes and create a git commit with a well-formatted message. Use when the user asks to commit, or when a workflow requires committing changes.
version: 1.0.0
---

# Git Commit Skill

Stage changes and commit with a message that follows project conventions.

## When to Use

- User explicitly asks to commit (`/commit`)
- Workflow step requires committing (development-workflow, process-protocol, git-worktree-workflow)

## Process

### Step 1: Read Rules

Read `.memory_bank/workflows/commit-message-rules.md` for the commit message conventions.

### Step 2: Analyze Changes

```bash
# Check what's staged
git diff --cached --stat

# If nothing staged, show unstaged changes
git diff --stat
git status -s
```

If nothing is staged, stage the relevant files first. Prefer `git add <specific files>` over `git add -A`. Never stage `.env`, credentials, or large binaries.

### Step 3: Understand the Diff

```bash
git diff --cached
```

Read the actual diff. Identify:
- The **main theme** of the changes
- Whether there are minor unrelated tweaks alongside

### Step 4: Compose Message and Commit

Apply the rules from Step 1. Then commit:

```bash
git commit -m "<message>"
```

If the message needs a body (rare), use a heredoc:

```bash
git commit -m "$(cat <<'EOF'
subject line

body line
EOF
)"
```

### Step 5: Verify

```bash
git log -1 --oneline
```
