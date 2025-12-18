# Validation Scripts

## validate-links.py

Validates Memory Bank link integrity after generation.

### What it checks

1. **File Existence**: All files from `.memory_bank/generation-plan.md` exist
2. **Index Links**: All markdown links in `index.md` files point to existing files
3. **Cross-References**: All markdown links in all `.md` files are valid

### Usage

```bash
# Run from project root (where .memory_bank/generation-plan.md exists)
python ${CLAUDE_PLUGIN_ROOT}/scripts/validate-links.py
```

### Output

**Success:**
```
✅ All 35 files exist
✅ All 48 index links valid
✅ All 127 cross-references valid
✅ All validation checks passed!
```

**Errors:**
```
❌ 2 files missing:
   - .memory_bank/guides/missing.md
   - .claude/agents/test.md

❌ 3 broken index links:
   - .memory_bank/guides/index.md: [Testing](../missing.md) → .memory_bank/missing.md

⚠️  5 broken cross-references:
   - .memory_bank/README.md: [Guide](./guides/old.md) → .memory_bank/guides/old.md

❌ Validation failed - fix errors above
```

### Exit codes

- `0`: All checks passed (or only warnings)
- `1`: Validation failed (missing files or broken index links)

### When to use

- Automatically in Phase 3 of `/create-ai-environment`
- Manually after editing Memory Bank files
- In CI/CD to catch broken links before deployment

## check-redundancy.py

Analyzes markdown files for redundant content and excessive verbosity.

### What it checks

1. **Repeated Phrases**: Detects 2-5 word phrases that appear multiple times
2. **Redundancy Percentage**: Calculates (repeated occurrences - unique count) / total phrases × 100
3. **Quality Threshold**: Flags files exceeding 10% redundancy

### Usage

```bash
# Check a single file
python scripts/check-redundancy.py .memory_bank/README.md

# Check multiple files
for file in .memory_bank/**/*.md; do
  python scripts/check-redundancy.py "$file"
done
```

### Output

**Optimal (≤10%):**
```
File: architecture.md
Lines: 615
Total phrases analyzed: 4522
Redundancy: 2.4%
✓ Redundancy optimal (2.4% ≤ 10%)
```

**High (>10%):**
```
File: verbose-file.md
Lines: 150
Total phrases analyzed: 2341
Redundancy: 15.8%

⚠️  High redundancy detected (15.8% > 10%)

Top repeated phrases:
  - 'memory bank documentation' (12 times)
  - 'project analysis json' (8 times)
  - 'generation plan md' (7 times)
  - 'static files to' (6 times)
  - 'prompt templates in' (5 times)
```

### Exit codes

- `0`: Redundancy ≤10% (optimal)
- `1`: Redundancy >10% (needs optimization)
- `2`: Error (file not found, invalid format, etc.)

### When to use

- During file generation to verify quality
- After manual edits to documentation
- Before running `/optimize-memory-bank` to identify targets
- In code review to maintain documentation standards
