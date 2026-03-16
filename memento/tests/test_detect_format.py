"""Tests for format command detection in detect-tech-stack."""

import importlib.util
from pathlib import Path

import pytest

# Load detect.py
_DETECT = Path(__file__).resolve().parents[1] / "skills" / "detect-tech-stack" / "scripts" / "detect.py"
_spec = importlib.util.spec_from_file_location("detect", _DETECT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

TechStackDetector = _mod.TechStackDetector


def _detect(tmp_path: Path) -> dict:
    """Run detection on a temp project and return the result."""
    detector = TechStackDetector(str(tmp_path))
    return detector.detect_all()


# ---------------------------------------------------------------------------
# Python format detection
# ---------------------------------------------------------------------------


_PYPROJECT_FLASK = '[project]\nname = "myapp"\ndependencies = ["flask>=3.0"]\n'


class TestPythonFormatDetection:
    def test_ruff_from_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(_PYPROJECT_FLASK + "\n[tool.ruff]\nline-length = 88\n")
        result = _detect(tmp_path)
        cmds = result.get("commands", {})
        assert "format_backend" in cmds
        assert "ruff format" in cmds["format_backend"]

    def test_ruff_from_ruff_toml(self, tmp_path):
        (tmp_path / "ruff.toml").write_text("line-length = 88\n")
        (tmp_path / "pyproject.toml").write_text(_PYPROJECT_FLASK)
        result = _detect(tmp_path)
        cmds = result.get("commands", {})
        assert "format_backend" in cmds
        assert "ruff format" in cmds["format_backend"]

    def test_black_from_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(_PYPROJECT_FLASK + "\n[tool.black]\nline-length = 88\n")
        result = _detect(tmp_path)
        cmds = result.get("commands", {})
        assert "format_backend" in cmds
        assert "black" in cmds["format_backend"]

    def test_no_formatter_detected(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(_PYPROJECT_FLASK)
        result = _detect(tmp_path)
        cmds = result.get("commands", {})
        assert "format_backend" not in cmds

    def test_ruff_with_uv_runner(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(_PYPROJECT_FLASK + "\n[tool.ruff]\nline-length = 88\n")
        (tmp_path / "uv.lock").write_text("")
        result = _detect(tmp_path)
        cmds = result.get("commands", {})
        assert cmds.get("format_backend", "").startswith("uv run ruff format")

    def test_ruff_wins_over_black(self, tmp_path):
        """When both ruff and black are configured, ruff format should win."""
        (tmp_path / "pyproject.toml").write_text(
            _PYPROJECT_FLASK + "\n[tool.ruff]\nline-length = 88\n\n[tool.black]\nline-length = 88\n"
        )
        result = _detect(tmp_path)
        cmds = result.get("commands", {})
        assert "format_backend" in cmds
        assert "ruff format" in cmds["format_backend"]
        assert "black" not in cmds["format_backend"]

    def test_recommendation_when_no_formatter(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(_PYPROJECT_FLASK + "\n[tool.flake8]\n")
        result = _detect(tmp_path)
        recs = result.get("recommendations", [])
        formatter_recs = [r for r in recs if r.get("category") == "formatter"]
        assert len(formatter_recs) == 1
        assert formatter_recs[0]["tool"] == "ruff"


# ---------------------------------------------------------------------------
# Node.js format detection
# ---------------------------------------------------------------------------


class TestNodeFormatDetection:
    @pytest.mark.parametrize("config_file", [".prettierrc", ".prettierrc.json"])
    def test_prettier_from_config(self, tmp_path, config_file):
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "4"}}')
        (tmp_path / config_file).write_text("{}\n")
        result = _detect(tmp_path)
        cmds = result.get("commands", {})
        assert "format_backend" in cmds
        assert "prettier" in cmds["format_backend"]

    def test_biome_from_config(self, tmp_path):
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "4"}}')
        (tmp_path / "biome.json").write_text("{}\n")
        result = _detect(tmp_path)
        cmds = result.get("commands", {})
        assert "format_backend" in cmds
        assert "biome format" in cmds["format_backend"]

    def test_format_script_in_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"express": "4"}, "scripts": {"format": "prettier --write ."}}'
        )
        result = _detect(tmp_path)
        cmds = result.get("commands", {})
        assert "format_backend" in cmds
        assert "run format" in cmds["format_backend"]

    def test_no_node_formatter(self, tmp_path):
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "4"}}')
        result = _detect(tmp_path)
        cmds = result.get("commands", {})
        assert "format_backend" not in cmds


# ---------------------------------------------------------------------------
# Frontend format detection
# ---------------------------------------------------------------------------


class TestFrontendFormatDetection:
    def test_prettier_frontend(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"react": "18"}, "scripts": {"format": "prettier --write src/"}}'
        )
        result = _detect(tmp_path)
        cmds = result.get("commands", {})
        assert "format_frontend" in cmds
        assert "run format" in cmds["format_frontend"]


# ---------------------------------------------------------------------------
# Monorepo cd prefix
# ---------------------------------------------------------------------------


class TestMonorepoFormatPrefix:
    def test_cd_prefix_for_subdirectory(self, tmp_path):
        """When ruff config is at root and backend is in subdirectory, format gets cd prefix."""
        backend = tmp_path / "backend"
        backend.mkdir()
        (backend / "pyproject.toml").write_text(_PYPROJECT_FLASK)
        # Ruff config at project root (detector looks at root for tool configs)
        (tmp_path / "ruff.toml").write_text("line-length = 88\n")
        result = _detect(tmp_path)
        cmds = result.get("commands", {})
        fmt = cmds.get("format_backend", "")
        assert fmt.startswith("cd backend && "), f"Expected cd prefix, got: {fmt}"
