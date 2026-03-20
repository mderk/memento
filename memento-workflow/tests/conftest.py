"""Shared test infrastructure for workflow engine tests.

Loads engine modules via exec() to avoid package import issues.
Provides namespace dicts that test files import from.

WARNING: The module-level _state_ns, _compiler_ns, _types_ns are shared across
all tests. Never mutate them directly — use monkeypatch or create fresh copies
via create_runner_ns().
"""

import re
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
ENGINE_DIR = SCRIPTS_DIR / "engine"
INFRA_DIR = SCRIPTS_DIR / "infra"


def _strip_relative_imports(code: str) -> str:
    """Remove all relative import statements from source code."""
    code = re.sub(r"from \.+\w+(?:\.\w+)* import \(.*?\)", "", code, flags=re.DOTALL)
    code = re.sub(r"from \.+\w+(?:\.\w+)* import .+", "", code)
    return code


def _exec_file(path: Path, ns: dict) -> None:
    """Read, strip relative imports, and exec a source file into namespace."""
    code = _strip_relative_imports(path.read_text())
    exec(compile(code, str(path), "exec"), ns)


# ---------------------------------------------------------------------------
# Types namespace
# ---------------------------------------------------------------------------

_types_ns: dict = {"__name__": "types", "__annotations__": {}}
exec(compile(
    (ENGINE_DIR / "types.py").read_text(),
    str(ENGINE_DIR / "types.py"), "exec",
), _types_ns)


def _public_types() -> dict:
    """Non-private symbols from types namespace."""
    return {k: v for k, v in _types_ns.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# State namespace (protocol + core + utils + actions + checkpoint + state)
# ---------------------------------------------------------------------------

_state_ns: dict = {
    "__name__": "state",
    "__annotations__": {},
    **_public_types(),
}
# Load engine modules
for _fname in ["protocol.py", "core.py"]:
    _exec_file(ENGINE_DIR / _fname, _state_ns)
# Load utils (scripts-level)
_exec_file(SCRIPTS_DIR / "utils.py", _state_ns)
# Load infra modules
for _fname in ["artifacts.py", "checkpoint.py"]:
    _exec_file(INFRA_DIR / _fname, _state_ns)
# Load remaining engine modules (depend on utils + infra)
for _fname in ["actions.py", "child_runs.py", "subworkflow.py", "parallel.py", "state.py"]:
    _exec_file(ENGINE_DIR / _fname, _state_ns)

# Enable _shell_log in test action responses (off by default in production)
_state_ns["INCLUDE_SHELL_LOG"] = True


# ---------------------------------------------------------------------------
# Compiler namespace
# ---------------------------------------------------------------------------

_compiler_ns: dict = {
    "__name__": "compiler",
    "__annotations__": {},
    "__builtins__": __builtins__,
    **_public_types(),
}
_exec_file(INFRA_DIR / "compiler.py", _compiler_ns)


# ---------------------------------------------------------------------------
# Loader namespace
# ---------------------------------------------------------------------------

_loader_ns: dict = {
    "__name__": "loader",
    "__annotations__": {},
    "__builtins__": __builtins__,
    "Path": Path,
    "compile_workflow": _compiler_ns["compile_workflow"],
    **_public_types(),
}
_exec_file(INFRA_DIR / "loader.py", _loader_ns)


# ---------------------------------------------------------------------------
# Runner namespace factory (each caller gets independent globals)
# ---------------------------------------------------------------------------


def create_runner_ns() -> dict:
    """Create a fresh runner namespace.

    Returns a new dict each time so test files that mutate runner globals
    don't interfere with each other.
    """
    from mcp.server.fastmcp import FastMCP

    ns: dict = {
        "__name__": "runner",
        "__annotations__": {},
        "__builtins__": __builtins__,
        "__file__": str(SCRIPTS_DIR / "runner.py"),
        "Path": Path,
        "FastMCP": FastMCP,
        **_public_types(),
        **{k: v for k, v in _state_ns.items() if not k.startswith("_")},
        **{k: v for k, v in _loader_ns.items() if not k.startswith("_")},
    }
    # Load extracted infra modules before runner.py (exec strips relative imports)
    _exec_file(INFRA_DIR / "sandbox.py", ns)
    _exec_file(INFRA_DIR / "shell_exec.py", ns)
    _exec_file(INFRA_DIR / "dashboard_helpers.py", ns)
    _exec_file(SCRIPTS_DIR / "runner.py", ns)
    return ns
