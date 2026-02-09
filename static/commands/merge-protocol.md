---
argument-hint: <protocol-path>
description: Merge a protocol branch into develop with code review
---

# Rule: Merge Protocol Branch

## Prerequisites

1. Read protocol plan.md to verify:
   - All steps are marked `[x]` (committed + reviewed)
   - Protocol worktree exists at `.worktrees/protocol-{NNNN}`
2. develop branch is clean

## Workflow

Follow **exactly** the merge procedure in:

**`.memory_bank/workflows/git-worktree-workflow.md` Phase 3 — Merge to Develop**

1. Final verification in worktree (tests, lint)
2. Code review on all changes vs develop (`git diff develop --stat`)
3. Run `/code-review` on modified files
4. Review iteration loop (fix, `/commit`, re-review until clean)
5. Ask user: merge / wait / review
6. Rebase onto develop
7. Merge with `--no-ff`
8. Verify tests on develop
9. Remove worktree
10. Delete branch
11. Update protocol status to `Complete` in plan.md
12. Remind about Memory Bank update — run `/update-memory-bank-protocol <protocol-path>`

## Code Review Scope

Review ALL changes between develop and the protocol branch:

```bash
cd ".worktrees/protocol-${PROTOCOL_NUM}"
git diff develop --stat
```

This reviews the cumulative effect of all steps together.

## User Confirmation

Always ask user before merging:

```
Protocol Ready for Merge
─────────────────────────────
Branch: protocol-{NNNN}
Changes vs develop: X files, +Y/-Z

Code review: PASSED
Tests: PASSED

Options:
1. [merge]  - Merge now and cleanup
2. [wait]   - Keep branch, merge later
3. [review] - Run another code review cycle
```

Default: wait

## Error Handling

| Error | Action |
|-------|--------|
| Steps not all `[x]` | Complete remaining steps first |
| Worktree not found | May already be merged, check plan.md |
| Merge conflict | Resolve in worktree, rebase, retry |
| Tests fail after merge | `git reset --hard HEAD~1`, fix in worktree |

## Success Report

After successful merge, report:

- Protocol name
- Merge commit hash
- Files changed, insertions, deletions
- Test results on develop
- Updated protocol status

```
Next steps:
- Run /update-memory-bank-protocol <protocol-path>
```
