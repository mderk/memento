---
name: check-redundancy
description: Analyze and report redundancy levels in markdown documentation files
version: 1.0.0
---

# Check Redundancy Skill

Analyzes markdown files for redundant content by detecting repeated phrases and calculating redundancy percentage.

## When to Use This Skill

Use this skill when:
- Reviewing generated Memory Bank documentation for quality
- Checking if a file needs optimization (redundancy > 10%)
- Validating documentation before committing
- During the file generation process to ensure optimal content

## What This Skill Does

1. **Analyzes repeated phrases** (2-5 words) in markdown files
2. **Filters common phrases** (articles, conjunctions, domain terms)
3. **Calculates redundancy percentage**: `(repeated occurrences - unique count) / total phrases × 100`
4. **Reports top repeated phrases** for manual review
5. **Exit codes**:
   - `0`: Optimal (≤10% redundancy)
   - `1`: High redundancy (>10%, needs optimization)
   - `2`: Error

## Usage

### Command Line

```bash
python .claude-plugin/skills/check-redundancy/scripts/check-redundancy.py <file>
```

### Example Output

```
File: architecture.md
Lines: 89
Total phrases analyzed: 1247
Redundancy: 3.2%
✓ Redundancy optimal (3.2% ≤ 10%)
```

Or if redundancy is high:

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

## Integration Examples

### In Generation Workflows

After generating a file:

```bash
# Generate file
python generate-doc.py > .memory_bank/file.md

# Check redundancy
python .claude-plugin/skills/check-redundancy/scripts/check-redundancy.py .memory_bank/file.md

# If exit code is 1, optimize the file
if [ $? -eq 1 ]; then
    echo "Optimizing file..."
    # Run optimization
fi
```

### In Batch Processing

```bash
for file in .memory_bank/**/*.md; do
    python .claude-plugin/skills/check-redundancy/scripts/check-redundancy.py "$file"
done
```

## How It Works

1. **Extract phrases**: Tokenizes text into 2-5 word phrases
2. **Filter noise**: Removes markdown syntax, code blocks, common English phrases
3. **Count frequencies**: Tracks how often each unique phrase appears
4. **Calculate redundancy**:
   - If "memory bank" appears 5 times, that's 4 redundant occurrences
   - Redundancy % = (total redundant occurrences) / (total phrases) × 100
5. **Report results**: Shows percentage and top repeated phrases

## Threshold

- **≤10% redundancy**: Optimal, file is concise
- **>10% redundancy**: High, file likely has repetitive content that can be consolidated

## Related

- `/optimize-memory-bank`: Optimizes all Memory Bank files with high redundancy
- `scripts/validate-links.py`: Validates links in Memory Bank files
- `.memory_bank/guides/code-review-guidelines.md`: Documentation quality standards
