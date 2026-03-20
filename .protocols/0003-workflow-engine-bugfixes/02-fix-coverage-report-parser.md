---
id: 02-fix-coverage-report-parser
status: pending
estimate: 30m
---
# Fix coverage report parser

## Objective

<!-- objective -->
Fix the coverage parser regex that captures wrong file's missing_lines, causing incorrect coverage data to be reported to the LLM during coverage-fill steps.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Tighten parse_coverage_report regex

The current regex `(.*?)$` captures anything to end of line as missing_lines. This is too permissive and can capture content from neighboring lines or invalid data.

- [ ] Change regex capture group for missing lines
  In `dev-tools.py` `parse_coverage_report()`, change the pytest regex:

  ```python
  # Before:
  r"^([\w/._-]+\.py)\s+\d+\s+\d+\s+(\d+)%\s*(.*?)$"

  # After:
  r"^([\w/._-]+\.py)\s+\d+\s+\d+\s+(\d+)%\s*([\d\-,\s]*)$"
  ```

  This constrains the missing_lines group to only match valid line-range syntax: digits, dashes (ranges), commas (separators), and whitespace.

- [ ] Add test for parse_coverage_report correctness
  Test cases:
  1. File with 100% coverage → empty missing_lines
  2. File with gaps → correct missing_lines list
  3. Multiple files in output → no cross-contamination
  4. TOTAL line not captured as a file entry

- [ ] Mirror dev-tools.py to .workflows/develop/
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- 100% coverage files must have empty missing_lines array
- Valid line ranges (42-50, 78) must still be captured correctly
- TOTAL line must not be matched as a file entry
- Must handle both branch and non-branch pytest output
<!-- /constraints -->

## Implementation Notes

The regex is at line ~284 of dev-tools.py. The jest/vitest regex on line ~300 may have a similar issue — check and fix if needed.

Test the regex against actual pytest term-missing output format:
```
Name                    Stmts   Miss  Cover   Missing
-----------------------------------------------------
scripts/engine/protocol.py   100     0   100%
scripts/engine/state.py      200    10    95%   42-50, 78
-----------------------------------------------------
TORAL                        300    10    97%
```

## Verification

<!-- verification -->
```bash
cd memento-workflow && uv run pytest
uv run pytest
diff memento/static/workflows/develop/dev-tools.py .workflows/develop/dev-tools.py
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento/static/workflows/develop/dev-tools.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
