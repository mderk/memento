"""Tests for sandbox-off audit warning (protocol 0004, step 02).

Verifies that _sandbox_prefix logs a warning when MEMENTO_SANDBOX=off,
and only logs once per process.
"""

import logging
from unittest.mock import patch

from conftest import create_runner_ns


class TestSandboxAuditWarning:
    def test_warning_logged_when_sandbox_off(self, caplog):
        """_sandbox_prefix should log a warning when sandbox is disabled."""
        ns = create_runner_ns()
        sandbox_prefix = ns["_sandbox_prefix"]

        # Reset the warned flag for this fresh namespace
        ns["_sandbox_off_warned"] = False

        with patch.dict("os.environ", {"MEMENTO_SANDBOX": "off"}):
            ns["SANDBOX_ENABLED"] = False
            with caplog.at_level(logging.WARNING, logger="workflow-engine"):
                result = sandbox_prefix("/tmp/test")
            assert result == []
            assert any("Sandbox disabled" in r.message for r in caplog.records), (
                "Expected 'Sandbox disabled' warning in log"
            )

    def test_warning_logged_only_once(self, caplog):
        """Warning should be logged at most once per process."""
        ns = create_runner_ns()
        sandbox_prefix = ns["_sandbox_prefix"]

        ns["_sandbox_off_warned"] = False

        with patch.dict("os.environ", {"MEMENTO_SANDBOX": "off"}):
            ns["SANDBOX_ENABLED"] = False
            with caplog.at_level(logging.WARNING, logger="workflow-engine"):
                sandbox_prefix("/tmp/test1")
                sandbox_prefix("/tmp/test2")
                sandbox_prefix("/tmp/test3")

            warnings = [r for r in caplog.records if "Sandbox disabled" in r.message]
            assert len(warnings) == 1, (
                f"Expected exactly 1 warning, got {len(warnings)}"
            )
