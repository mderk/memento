"""Tests for relay protocol documentation — SKILL.md must document prompt_file."""

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
