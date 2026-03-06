# Commit Message Rules

## Format

- **Language**: English, always
- **Subject line**: up to 72 characters, no period at the end
- **Prefix**: one of `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`
- **Mood**: imperative — "add validation", not "added validation"
- **Body**: optional, separated by blank line, only when subject alone is not enough

## Content

- Write **why**, not **what** — the diff shows what changed
- Focus on the **main theme**; if minor unrelated tweaks are included, don't mention them
- Keep it to **1-2 lines** max (subject + optional one-line body)
- No file lists — that's what `git diff` is for

## Forbidden

- No `Co-Authored-By` or any AI attribution lines
- No vague messages: ~~"minor fixes"~~, ~~"update"~~, ~~"changes"~~, ~~"misc"~~
- No prefix duplication: ~~"fix: fix the bug"~~
- No emoji in messages

## Examples

Good:
```
feat: add rate limiting to /api/auth endpoints
```
```
fix: prevent duplicate webhook delivery on retry
```
```
refactor: extract email validation into shared util
```

Bad:
```
update files                          # vague
fix: fix login                        # prefix duplication, no context
feat: add new feature for users       # says nothing
Updated auth, fixed typo in readme    # past tense, mixes topics, no prefix
```
