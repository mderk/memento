---
description: Find and fix broken links in Memory Bank files
---

# Fix Broken Links

This command invokes the `fix-broken-links` skill to validate and fix broken links in Memory Bank.

## Usage

Simply run this command and the skill will:

1. Run validation script to scan `.memory_bank/` directory
2. Report broken links if found
3. Fix each broken link automatically
4. Re-validate to confirm fixes
5. Provide summary of changes

## What it Does

The skill will automatically:

-   Scan all `.memory_bank/` files for broken links
-   Check UTF-8 encoding
-   Validate all `index.md` links
-   Validate all cross-references
-   Fix broken links by:
    -   Updating to similar files if found
    -   Removing unnecessary links
    -   Removing obsolete sections
-   Report all changes made

## Skill Reference

This command uses the **fix-broken-links** skill, which is included in the memento plugin.

See `.claude/skills/fix-broken-links/SKILL.md` for detailed documentation on how the skill works.
