"""Verify _dsl.py stubs stay in sync with types.py block definitions.

Parses both files via AST and checks that every Block subclass in types.py
has a corresponding stub class in _dsl.py with matching __init__ parameters.
"""

import ast
from pathlib import Path

import pytest

TYPES_PY = Path(__file__).resolve().parents[1] / "scripts" / "engine" / "types.py"
DSL_PY = Path(__file__).resolve().parents[2] / "memento" / "static" / "workflows" / "_dsl.py"


def _parse_types_classes() -> dict[str, set[str]]:
    """Extract block classes and their field names from types.py.

    Returns {ClassName: {field_name, ...}} for BlockBase subclasses
    and other relevant classes (WorkflowDef, Branch, WorkflowContext).
    """
    tree = ast.parse(TYPES_PY.read_text())
    block_bases: set[str] = set()
    classes: dict[str, set[str]] = {}

    # First pass: find BlockBase and its subclasses
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            base_names = [
                b.id for b in node.bases if isinstance(b, ast.Name)
            ]
            if node.name == "BlockBase":
                block_bases.add(node.name)
            elif any(b in block_bases for b in base_names):
                block_bases.add(node.name)

    # Target classes: all BlockBase subclasses + WorkflowDef + Branch
    target = block_bases | {"WorkflowDef", "Branch", "WorkflowContext"}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in target:
            fields: set[str] = set()
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    name = item.target.id
                    # Skip private attrs and 'type' discriminator
                    if not name.startswith("_") and name != "model_config":
                        fields.add(name)
            classes[node.name] = fields

    # Propagate BlockBase fields to subclasses
    base_fields = classes.get("BlockBase", set())
    for cls_name in block_bases:
        if cls_name != "BlockBase" and cls_name in classes:
            classes[cls_name] = classes[cls_name] | base_fields

    return classes


def _parse_dsl_stubs() -> dict[str, set[str]]:
    """Extract stub class __init__ parameter names from _dsl.py.

    Returns {ClassName: {param_name, ...}} excluding 'self' and **kwargs.
    """
    tree = ast.parse(DSL_PY.read_text())
    classes: dict[str, set[str]] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            params: set[str] = set()
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    for arg in item.args.args:
                        if arg.arg != "self":
                            params.add(arg.arg)
                    for arg in item.args.kwonlyargs:
                        params.add(arg.arg)
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    # WorkflowContext uses plain annotations instead of __init__
                    params.add(item.target.id)
                elif isinstance(item, ast.FunctionDef) and item.name != "__init__":
                    # Methods like get_var, result_field — skip
                    pass
            # Discard catch-all **kwargs marker
            params.discard("kwargs")
            if params:
                classes[node.name] = params

    return classes


# Shared between classes that should exist in _dsl.py
# BlockBase is not directly in _dsl.py — its fields are on each stub
_SKIP_CLASSES = {"BlockBase", "StepResult"}


class TestDslParity:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.types_classes = _parse_types_classes()
        self.dsl_stubs = _parse_dsl_stubs()

    def test_all_block_types_have_stubs(self):
        """Every Block subclass in types.py must have a stub in _dsl.py."""
        missing = set()
        for cls_name in self.types_classes:
            if cls_name in _SKIP_CLASSES:
                continue
            if cls_name not in self.dsl_stubs:
                missing.add(cls_name)
        assert not missing, f"Block types missing from _dsl.py: {missing}"

    def test_stub_fields_match(self):
        """Each stub must have all fields from the real class."""
        errors = []
        for cls_name, fields in self.types_classes.items():
            if cls_name in _SKIP_CLASSES:
                continue
            stub_params = self.dsl_stubs.get(cls_name, set())
            if not stub_params:
                continue
            # Fields that are in types.py but missing from _dsl.py stub
            # Exclude 'type' (discriminator, not user-facing)
            check_fields = fields - {"type"}
            missing = check_fields - stub_params
            if missing:
                errors.append(f"{cls_name}: missing {sorted(missing)}")
        assert not errors, "Field mismatches:\n" + "\n".join(errors)

    def test_no_extra_stub_params(self):
        """Stub __init__ should not have params that don't exist in types.py.

        Catches renamed/removed fields that weren't cleaned up in _dsl.py.
        Allows **kwargs catch-all (already stripped by parser).
        """
        errors = []
        for cls_name, stub_params in self.dsl_stubs.items():
            real_fields = self.types_classes.get(cls_name, set())
            if not real_fields:
                continue
            # Exclude 'type' from real fields — stubs don't need it
            extra = stub_params - real_fields - {"type"}
            if extra:
                errors.append(f"{cls_name}: extra stub params {sorted(extra)}")
        assert not errors, "Extra stub params:\n" + "\n".join(errors)
