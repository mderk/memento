"""Tests for relay protocol documentation — SKILL.md relay loop and watchdog."""

from pathlib import Path

SKILL_MD = (
    Path(__file__).resolve().parent.parent / "skills" / "workflow-engine" / "SKILL.md"
)


class TestRelayProtocolDocs:
    def test_skill_md_documents_prompt_file(self):
        """SKILL.md prompt handler should mention prompt_file."""
        content = SKILL_MD.read_text()
        assert "prompt_file" in content

    def test_skill_md_has_backward_compatibility_note(self):
        """SKILL.md should document backward compatibility for old relays."""
        content = SKILL_MD.read_text()
        # Should mention that old relays see a stub
        assert "stub" in content.lower() or "backward" in content.lower()

    def test_skill_md_documents_schema_file(self):
        """SKILL.md prompt handler should mention schema_file."""
        content = SKILL_MD.read_text()
        assert "schema_file" in content

    def test_skill_md_documents_schema_id(self):
        """SKILL.md should mention schema_id for relay caching."""
        content = SKILL_MD.read_text()
        assert "schema_id" in content

    def test_skill_md_documents_compact_mode(self):
        """SKILL.md completed handler should mention compact mode."""
        content = SKILL_MD.read_text()
        assert "compact" in content.lower()


class TestRelayLoopStrength:
    """Relay loop steps must be explicit about continuation and termination."""

    def test_step5_says_immediately(self):
        """Step 5 must tell the agent to go back immediately."""
        content = SKILL_MD.read_text()
        assert "immediately" in content.lower()

    def test_step6_lists_terminal_actions(self):
        """Step 6 must list all terminal actions so the agent knows when to stop."""
        content = SKILL_MD.read_text()
        for action in ("completed", "halted", "error"):
            assert f'"action": "{action}"' in content

    def test_never_break_the_loop_paragraph(self):
        """A 'Never break the loop' paragraph must follow the relay loop steps."""
        content = SKILL_MD.read_text()
        assert "never break the loop" in content.lower()

    def test_key_rules_has_never_break(self):
        """Key Rules section must include a 'Never break the relay loop' bullet."""
        content = SKILL_MD.read_text()
        # Find Key Rules section and check it contains the bullet
        key_rules_idx = content.find("## Key Rules")
        assert key_rules_idx != -1, "Key Rules section missing"
        key_rules_section = content[key_rules_idx:]
        assert "never break the relay loop" in key_rules_section.lower()


class TestRelayWatchdogDocs:
    """SKILL.md must document the relay watchdog mechanism."""

    def test_watchdog_section_exists(self):
        """A Relay Watchdog section must exist."""
        content = SKILL_MD.read_text()
        assert "## Relay Watchdog" in content

    def test_watchdog_explains_stop_hook(self):
        """Watchdog section must mention the Stop hook mechanism."""
        content = SKILL_MD.read_text()
        watchdog_idx = content.find("## Relay Watchdog")
        assert watchdog_idx != -1
        watchdog_section = content[watchdog_idx:]
        assert (
            "stop hook" in watchdog_section.lower() or "Stop hook" in watchdog_section
        )

    def test_watchdog_mentions_next_recovery(self):
        """Watchdog section must instruct to call next(run_id) for recovery."""
        content = SKILL_MD.read_text()
        watchdog_idx = content.find("## Relay Watchdog")
        assert watchdog_idx != -1
        watchdog_section = content[watchdog_idx:]
        assert "next(run_id)" in watchdog_section or "next" in watchdog_section.lower()

    def test_watchdog_mentions_max_retries(self):
        """Watchdog section must mention the retry limit (3 attempts)."""
        content = SKILL_MD.read_text()
        watchdog_idx = content.find("## Relay Watchdog")
        assert watchdog_idx != -1
        watchdog_section = content[watchdog_idx:]
        assert "3" in watchdog_section
