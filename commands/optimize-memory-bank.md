---
description: Scan and optimize Memory Bank files for redundancy
---

# Optimize Memory Bank for Redundancy

## Safety: Create Backup

**CRITICAL**: Before any changes:
```bash
cp -r .memory_bank .memory_bank.backup.$(date +%Y%m%d_%H%M%S)
```

Backup created at: `.memory_bank.backup.YYYYMMDD_HHMMSS`

## Optimization Process

1. **Load redundancy patterns ONCE** (reuse for all files):
   - Load common redundancy patterns and detection rules
   - Prepare optimization strategies for identified patterns

2. **Scan files**: Find all `.memory_bank/**/*.md` files using Glob

3. **For EACH file** (sequential, no subagents):

   a. **Read and analyze**:
      - Read file content
      - Count lines (before_lines)
      - Report: `🔍 Checking [filename] (X lines)...`

   b. **Check redundancy**:
      - Apply redundancy pattern detection
      - Calculate redundancy percentage

   c. **Optimize if needed**:
      - If redundancy >10%:
        - Apply optimization fixes for detected patterns
        - Preserve unique content (never lose information)
        - Target: 30-50% reduction
        - Overwrite file with optimized version
        - Count new lines (after_lines)
        - Calculate reduction: `((before - after) / before) * 100`
        - Report: `✅ Optimized [filename]: X → Y lines (-Z%)`
      - If redundancy ≤10%:
        - Keep original unchanged
        - Report: `✅ [filename] already optimal`

   d. **Track metrics**: Add to running totals (files_optimized, total_lines_saved)

4. **Final report**: Show summary with before/after metrics

## Expected Results

**Typical outcomes:**
- 30-50% reduction in verbose files
- Preserved content quality
- Improved consistency
- Faster context loading

**Report example:**
```
✓ Scanned 28 files
✓ Optimized 12 files (43%)
✓ Saved 1,850 lines (38% average reduction)
✓ Backup: .memory_bank.backup.20251114_143022

Top improvements:
  - tech_stack.md: 648 → 301 lines (-54%)
  - current_tasks.md: 573 → 174 lines (-70%)
  - ai-agent-handbook.md: 404 → 251 lines (-38%)
```
