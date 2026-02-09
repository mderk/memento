---
argument-hint: <protocol-path> <step-number>
description: Merge an approved protocol step's worktree into develop (per-step strategy only)
---

# Rule: Merge Protocol Step

**Only for `per-step` branching strategy.** For `per-protocol`/`per-group`, use `/merge-protocol`.

## Prerequisites

Before merging, verify:

1. Protocol branching strategy is `per-step` (check plan.md)
2. Step status is `[✓]` Approved in plan.md Progress section
3. Worktree exists at `.worktrees/protocol-{NNNN}-step-{MM}`
4. No uncommitted changes in worktree
5. develop branch is clean

## Workflow

Follow **exactly** the merge procedure in:

**`.memory_bank/workflows/git-worktree-workflow.md` Phase 3 — "For per-step"**

Key steps:

1. Final verification in worktree (tests, lint)
2. Rebase onto develop
3. Merge with `--no-ff`
4. Verify tests on develop
5. Remove worktree
6. Delete branch
7. Update status to `[M]` Merged in plan.md

## Error Handling

| Error | Action |
|-------|--------|
| Strategy is not per-step | Use `/merge-protocol` instead |
| Step not approved `[✓]` | Run code review first |
| Worktree not found | Step may already be merged, check plan.md |
| Merge conflict | Resolve in worktree, rebase, retry |
| Tests fail after merge | `git reset --hard HEAD~1`, fix in worktree |

## Success Report

After successful merge, report:

- Merge commit hash
- Test results on develop
- Updated step status in plan.md
- Next pending steps (if any)
