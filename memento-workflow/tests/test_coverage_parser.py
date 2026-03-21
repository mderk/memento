"""Tests for parse_coverage_report regex correctness (protocol 0003, step 02).

Verifies:
- 100% coverage files have empty missing_lines
- Files with gaps have correct missing_lines
- No cross-file contamination between adjacent entries
- TOTAL line is not matched as a file entry
"""

import importlib.util
import sys
from pathlib import Path

# Load dev-tools.py to get parse_coverage_report
REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_TOOLS = REPO_ROOT / "memento" / "static" / "workflows" / "develop" / "dev-tools.py"


def _load_parse_coverage():
    """Load parse_coverage_report from dev-tools.py."""
    spec = importlib.util.spec_from_file_location("dev_tools", DEV_TOOLS)
    mod = importlib.util.module_from_spec(spec)
    # dev-tools.py needs argparse etc. in its namespace
    old_argv = sys.argv
    sys.argv = ["dev-tools.py"]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = old_argv
    return mod.parse_coverage_report


parse_coverage_report = _load_parse_coverage()

PYTEST_OUTPUT = """\
---------- coverage: platform darwin, python 3.12.0 ----------
Name                              Stmts   Miss  Cover   Missing
---------------------------------------------------------------
scripts/engine/protocol.py          100      0   100%
scripts/engine/state.py             200     10    95%   42-50, 78
scripts/engine/actions.py            80      5    94%   15, 30-35
tests/test_sandbox.py                76      0   100%
---------------------------------------------------------------
TOTAL                               456     15    97%
"""


class TestParseCoverageReport:
    """Verify pytest coverage parser correctness."""

    def test_100pct_file_has_empty_missing_lines(self):
        """Files with 100% coverage must have empty missing_lines."""
        result = parse_coverage_report(PYTEST_OUTPUT, "pytest")
        protocol = next(
            f for f in result["coverage_details"]
            if f["file"] == "scripts/engine/protocol.py"
        )
        assert protocol["coverage_pct"] == 100.0
        assert protocol["missing_lines"] == []

    def test_file_with_gaps_has_correct_missing_lines(self):
        """Files with gaps must have correct line ranges."""
        result = parse_coverage_report(PYTEST_OUTPUT, "pytest")
        state = next(
            f for f in result["coverage_details"]
            if f["file"] == "scripts/engine/state.py"
        )
        assert state["coverage_pct"] == 95.0
        assert state["missing_lines"] == ["42-50", "78"]

    def test_no_cross_file_contamination(self):
        """Each file entry must have only its own missing_lines."""
        result = parse_coverage_report(PYTEST_OUTPUT, "pytest")
        for entry in result["coverage_details"]:
            for line in entry["missing_lines"]:
                # Missing lines should only contain digits, dashes, and spaces
                assert all(c in "0123456789-, " for c in line), (
                    f"File {entry['file']} has invalid missing_lines entry: '{line}'. "
                    "Likely cross-file contamination."
                )

    def test_total_not_captured_as_file(self):
        """TOTAL line must not appear as a file entry."""
        result = parse_coverage_report(PYTEST_OUTPUT, "pytest")
        file_names = [f["file"] for f in result["coverage_details"]]
        assert "TOTAL" not in file_names

    def test_total_percentage_parsed(self):
        """Overall total percentage must be extracted."""
        result = parse_coverage_report(PYTEST_OUTPUT, "pytest")
        assert result["coverage_pct"] == 97.0

    def test_multiple_100pct_files_all_have_empty_missing(self):
        """All 100% files must have empty missing_lines (no leakage from neighbors)."""
        result = parse_coverage_report(PYTEST_OUTPUT, "pytest")
        full_coverage_files = [
            f for f in result["coverage_details"]
            if f["coverage_pct"] == 100.0
        ]
        assert len(full_coverage_files) == 2  # protocol.py and test_sandbox.py
        for entry in full_coverage_files:
            assert entry["missing_lines"] == [], (
                f"{entry['file']} has 100% coverage but missing_lines={entry['missing_lines']}"
            )
