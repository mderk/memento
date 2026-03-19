"""Tests for protocol_md.py — markdown primitives and protocol renderer."""

import json
from pathlib import Path

PROTOCOL_MD_PATH = Path(__file__).resolve().parent.parent / "static" / "workflows" / "process-protocol" / "protocol_md.py"

_ns: dict = {"__name__": "protocol_md", "__file__": str(PROTOCOL_MD_PATH), "__annotations__": {}}
exec(compile(PROTOCOL_MD_PATH.read_text(), str(PROTOCOL_MD_PATH), "exec"), _ns)

read_frontmatter = _ns["read_frontmatter"]
extract_between_markers = _ns["extract_between_markers"]
render_step_body = _ns["render_step_body"]
render_step_file = _ns["render_step_file"]
render_plan_md = _ns["render_plan_md"]
render_protocol = _ns["render_protocol"]
_render_task_item = _ns["_render_task_item"]
_render_task = _ns["_render_task"]


# ============ TaskItem Rendering ============


class TestRenderTaskItem:
    def test_simple_item(self):
        result = _render_task_item({"title": "Add login endpoint"})
        assert result == "- [ ] Add login endpoint"

    def test_item_with_body(self):
        result = _render_task_item({
            "title": "Edit `auth.py`",
            "body": "Remove old middleware.\nAdd new PKCE flow.",
        })
        assert "- [ ] Edit `auth.py`" in result
        assert "  Remove old middleware." in result
        assert "  Add new PKCE flow." in result

    def test_item_with_subtasks(self):
        result = _render_task_item({
            "title": "Refactor config",
            "subtasks": [
                {"title": "Extract constants"},
                {"title": "Update imports"},
            ],
        })
        assert "- [ ] Refactor config" in result
        assert "  - [ ] Extract constants" in result
        assert "  - [ ] Update imports" in result

    def test_item_with_body_and_subtasks(self):
        result = _render_task_item({
            "title": "Edit `product_brief.md.prompt`",
            "body": "Remove Technology Stack section (§2).",
            "subtasks": [
                {"title": "Remove section"},
                {"title": "Add cross-reference"},
            ],
        })
        lines = result.splitlines()
        assert lines[0] == "- [ ] Edit `product_brief.md.prompt`"
        assert "  Remove Technology Stack section" in result
        assert "  - [ ] Remove section" in result
        assert "  - [ ] Add cross-reference" in result

    def test_nested_subtasks(self):
        result = _render_task_item({
            "title": "Top level",
            "subtasks": [{
                "title": "Mid level",
                "subtasks": [{"title": "Deep level"}],
            }],
        })
        assert "- [ ] Top level" in result
        assert "  - [ ] Mid level" in result
        assert "    - [ ] Deep level" in result


# ============ Task Rendering ============


class TestRenderTask:
    def test_task_with_heading_and_subtasks(self):
        result = _render_task({
            "heading": "Recompute hashes",
            "subtasks": [
                {"title": "Run recompute script"},
                {"title": "Verify no diff"},
            ],
        })
        assert "<!-- task -->" in result
        assert "### Recompute hashes" in result
        assert "- [ ] Run recompute script" in result
        assert "- [ ] Verify no diff" in result
        assert "<!-- /task -->" in result

    def test_task_with_description(self):
        result = _render_task({
            "heading": "Setup infrastructure",
            "description": "Configure the base project structure.",
            "subtasks": [{"title": "Create directories"}],
        })
        assert "Configure the base project structure." in result
        assert "- [ ] Create directories" in result

    def test_task_no_subtasks(self):
        result = _render_task({
            "heading": "Review",
            "description": "Final review of changes.",
        })
        assert "<!-- task -->" in result
        assert "### Review" in result
        assert "Final review of changes." in result
        assert "<!-- /task -->" in result


# ============ Step Body Rendering ============


class TestRenderStepBody:
    def test_minimal_step(self):
        step = {
            "name": "Setup",
            "objective": "Initialize the project.",
            "tasks": [{"heading": "Init", "subtasks": [{"title": "Create repo"}]}],
            "constraints": ["Must use existing tooling"],
            "verification": ["pytest tests/"],
            "estimate": "2h",
        }
        body = render_step_body(step)
        assert "# Setup" in body
        assert "<!-- objective -->" in body
        assert "Initialize the project." in body
        assert "<!-- /objective -->" in body
        assert "<!-- tasks -->" in body
        assert "### Init" in body
        assert "- [ ] Create repo" in body
        assert "<!-- /tasks -->" in body
        assert "<!-- constraints -->" in body
        assert "Must use existing tooling" in body
        assert "<!-- verification -->" in body
        assert "pytest tests/" in body
        assert "<!-- findings -->" in body
        assert "<!-- /findings -->" in body
        assert "None expected" in body

    def test_step_with_all_optional_fields(self):
        step = {
            "name": "Full Step",
            "objective": "Do everything.",
            "tasks": [{"heading": "Work", "subtasks": [{"title": "Task 1"}]}],
            "constraints": ["Constraint 1"],
            "impl_notes": "Key files:\n- src/main.py",
            "verification": ["pytest", "ruff check ."],
            "context_files": [".memory_bank/patterns/api.md"],
            "starting_points": ["src/main.py", "src/config.py"],
            "memory_bank_impact": ["Update patterns/api.md with new endpoints"],
            "estimate": "4h",
        }
        body = render_step_body(step)
        assert "## Implementation Notes" in body
        assert "src/main.py" in body
        assert "<!-- context:files -->" in body
        assert ".memory_bank/patterns/api.md" in body
        assert "<!-- starting_points -->" in body
        assert "src/config.py" in body
        assert "Update patterns/api.md" in body
        assert "None expected" not in body

    def test_step_no_constraints(self):
        step = {
            "name": "Simple",
            "objective": "Just do it.",
            "tasks": [],
            "constraints": [],
            "verification": [],
            "estimate": "1h",
        }
        body = render_step_body(step)
        assert "<!-- constraints -->" not in body
        assert "<!-- verification -->" not in body


# ============ Step File Rendering ============


class TestRenderStepFile:
    def test_frontmatter(self):
        step = {
            "name": "Setup",
            "objective": "Init.",
            "tasks": [],
            "constraints": [],
            "verification": [],
            "estimate": "2h",
        }
        content = render_step_file(step, "01-setup")
        assert content.startswith("---\n")
        assert "id: 01-setup" in content
        assert "status: pending" in content
        assert "estimate: 2h" in content

    def test_roundtrip_frontmatter(self, tmp_path):
        """Written step file can be parsed back by read_frontmatter."""
        step = {
            "name": "Database",
            "objective": "Set up DB.",
            "tasks": [{"heading": "Migrate", "subtasks": [{"title": "Run alembic"}]}],
            "constraints": ["Must be reversible"],
            "verification": ["alembic upgrade head"],
            "estimate": "3h",
        }
        content = render_step_file(step, "02-db")
        f = tmp_path / "02-db.md"
        f.write_text(content, encoding="utf-8")

        fm, body = read_frontmatter(f)
        assert fm["id"] == "02-db"
        assert fm["status"] == "pending"
        assert fm["estimate"] == "3h"

        # Markers can be extracted
        obj = extract_between_markers(body, "objective")
        assert obj == "Set up DB."
        tasks = extract_between_markers(body, "tasks")
        assert "### Migrate" in tasks
        assert "- [ ] Run alembic" in tasks
        constraints = extract_between_markers(body, "constraints")
        assert "Must be reversible" in constraints


# ============ Plan.md Rendering ============


class TestRenderPlanMd:
    def test_basic_plan(self):
        protocol = {
            "name": "Feature X",
            "context": "We need feature X.",
            "decision": "Build it incrementally.",
            "rationale": "Reduces risk.",
            "consequences_positive": ["Better UX"],
            "consequences_negative": ["More complexity"],
        }
        entries = [
            {"name": "Setup", "path": "01-setup.md", "id": "01-setup", "estimate": "2h"},
            {"name": "Database", "path": "02-db.md", "id": "02-db", "estimate": "3h"},
        ]
        result = render_plan_md(protocol, entries, today="2026-03-19")

        assert "# Protocol: Feature X" in result
        assert "**Created**: 2026-03-19" in result
        assert "We need feature X." in result
        assert "Build it incrementally." in result
        assert "Reduces risk." in result
        assert "- Better UX" in result
        assert "- More complexity" in result
        assert "- [ ] [Setup](./01-setup.md) <!-- id:01-setup --> — 2h est" in result
        assert "- [ ] [Database](./02-db.md) <!-- id:02-db --> — 3h est" in result

    def test_plan_with_groups(self):
        protocol = {
            "name": "Big Feature",
            "context": "Context.",
            "decision": "Decision.",
            "rationale": "Rationale.",
            "consequences_positive": [],
            "consequences_negative": [],
        }
        entries = [
            {"name": "Init", "path": "01-init.md", "id": "01-init", "estimate": "1h"},
            {
                "name": "Schema",
                "path": "02-infra/01-schema.md",
                "id": "02-infra-01-schema",
                "estimate": "2h",
                "group": "Infrastructure (02-infra/)",
            },
            {
                "name": "API",
                "path": "02-infra/02-api.md",
                "id": "02-infra-02-api",
                "estimate": "3h",
                "group": "Infrastructure (02-infra/)",
            },
            {"name": "Testing", "path": "03-testing.md", "id": "03-testing", "estimate": "2h"},
        ]
        result = render_plan_md(protocol, entries, today="2026-03-19")

        assert "### Infrastructure (02-infra/)" in result
        assert "- [ ] [Schema](./02-infra/01-schema.md)" in result
        assert "- [ ] [API](./02-infra/02-api.md)" in result
        # Group header should appear only once
        assert result.count("### Infrastructure") == 1


# ============ Full Protocol Rendering ============


class TestRenderProtocol:
    def _make_protocol(self):
        return {
            "name": "Admin Dashboard",
            "context": "Need admin UI.",
            "decision": "Build with existing framework.",
            "rationale": "Fastest approach.",
            "consequences_positive": ["Quick delivery"],
            "consequences_negative": ["Limited customization"],
            "items": [
                {
                    "name": "Setup Layout",
                    "objective": "Create base layout.",
                    "tasks": [
                        {
                            "heading": "Scaffold components",
                            "subtasks": [
                                {"title": "Create sidebar"},
                                {"title": "Create header"},
                            ],
                        },
                    ],
                    "constraints": ["Use design system"],
                    "verification": ["npm test"],
                    "estimate": "3h",
                },
                {
                    "title": "Data Layer",
                    "steps": [
                        {
                            "name": "Database Schema",
                            "objective": "Define tables.",
                            "tasks": [{"heading": "Create migrations", "subtasks": [{"title": "Add users table"}]}],
                            "constraints": ["Must be reversible"],
                            "verification": ["alembic upgrade head"],
                            "estimate": "2h",
                        },
                        {
                            "name": "API Endpoints",
                            "objective": "Build REST API.",
                            "tasks": [{"heading": "CRUD routes", "subtasks": [{"title": "GET /users"}]}],
                            "constraints": [],
                            "verification": ["pytest tests/api/"],
                            "estimate": "4h",
                        },
                    ],
                },
                {
                    "name": "Testing",
                    "objective": "Full test coverage.",
                    "tasks": [{"heading": "Write tests", "subtasks": [{"title": "E2E tests"}]}],
                    "constraints": [],
                    "verification": ["pytest"],
                    "estimate": "2h",
                },
            ],
        }

    def test_creates_directory_structure(self, tmp_path):
        proto = self._make_protocol()
        result = render_protocol(proto, tmp_path / "protocol", today="2026-03-19")

        out = tmp_path / "protocol"
        assert (out / "plan.md").is_file()
        assert (out / "01-setup-layout.md").is_file()
        assert (out / "02-data-layer").is_dir()
        assert (out / "02-data-layer" / "01-database-schema.md").is_file()
        assert (out / "02-data-layer" / "02-api-endpoints.md").is_file()
        assert (out / "03-testing.md").is_file()

        assert result["step_count"] == 4
        assert "plan.md" in result["files_created"]

    def test_step_files_have_valid_frontmatter(self, tmp_path):
        proto = self._make_protocol()
        render_protocol(proto, tmp_path / "protocol", today="2026-03-19")

        out = tmp_path / "protocol"

        # Root step
        fm, body = read_frontmatter(out / "01-setup-layout.md")
        assert fm["id"] == "01-setup-layout"
        assert fm["status"] == "pending"
        assert fm["estimate"] == "3h"
        assert "<!-- objective -->" in body
        assert "Create base layout." in body

        # Group step
        fm, body = read_frontmatter(out / "02-data-layer" / "01-database-schema.md")
        assert fm["id"] == "02-data-layer-01-database-schema"
        assert fm["estimate"] == "2h"

    def test_plan_md_has_correct_progress(self, tmp_path):
        proto = self._make_protocol()
        render_protocol(proto, tmp_path / "protocol", today="2026-03-19")

        plan = (tmp_path / "protocol" / "plan.md").read_text()
        assert "# Protocol: Admin Dashboard" in plan
        assert "<!-- id:01-setup-layout -->" in plan
        assert "<!-- id:02-data-layer-01-database-schema -->" in plan
        assert "<!-- id:02-data-layer-02-api-endpoints -->" in plan
        assert "<!-- id:03-testing -->" in plan
        assert "### Data Layer (02-data-layer/)" in plan

    def test_step_files_parseable_by_helpers(self, tmp_path):
        """Generated step files can be parsed by process-protocol helpers."""
        proto = self._make_protocol()
        render_protocol(proto, tmp_path / "protocol", today="2026-03-19")

        out = tmp_path / "protocol"
        step = out / "01-setup-layout.md"
        _, body = read_frontmatter(step)

        # Task markers are extractable
        tasks = extract_between_markers(body, "tasks")
        assert tasks is not None
        assert "<!-- task -->" in tasks
        assert "### Scaffold components" in tasks
        assert "- [ ] Create sidebar" in tasks

        # Constraint markers
        constraints = extract_between_markers(body, "constraints")
        assert "Use design system" in constraints

    def test_item_wrapper_format(self, tmp_path):
        """Renderer handles ItemWrapper format from Pydantic structured output."""
        proto = {
            "name": "Wrapper Test",
            "context": "Context.",
            "decision": "Decision.",
            "rationale": "Rationale.",
            "consequences_positive": ["Good"],
            "consequences_negative": ["Bad"],
            "items": [
                {"type": "step", "step": {
                    "name": "Root Step",
                    "objective": "Do root thing.",
                    "tasks": [{"heading": "Init", "subtasks": [{"title": "Setup"}]}],
                    "constraints": [],
                    "verification": [],
                    "estimate": "1h",
                }},
                {"type": "group", "group": {
                    "title": "Grouped",
                    "steps": [{
                        "name": "Inner Step",
                        "objective": "Do inner thing.",
                        "tasks": [{"heading": "Work", "subtasks": [{"title": "Build"}]}],
                        "constraints": [],
                        "verification": [],
                        "estimate": "2h",
                    }],
                }},
            ],
        }
        result = render_protocol(proto, tmp_path / "out", today="2026-03-19")
        out = tmp_path / "out"

        assert result["step_count"] == 2
        assert (out / "01-root-step.md").is_file()
        assert (out / "02-grouped" / "01-inner-step.md").is_file()

        # Verify frontmatter is correct
        fm, body = read_frontmatter(out / "01-root-step.md")
        assert fm["id"] == "01-root-step"
        assert "Do root thing." in body

        fm2, body2 = read_frontmatter(out / "02-grouped" / "01-inner-step.md")
        assert fm2["id"] == "02-grouped-01-inner-step"
        assert "Do inner thing." in body2

        # plan.md has correct entries
        plan = (out / "plan.md").read_text()
        assert "<!-- id:01-root-step -->" in plan
        assert "<!-- id:02-grouped-01-inner-step -->" in plan
        assert "### Grouped (02-grouped/)" in plan

    def test_pydantic_schema_matches_renderer(self):
        """Pydantic models in create-protocol/workflow.py match what render_protocol expects.

        Guards against schema drift: if a Pydantic field is renamed, this test
        catches that the renderer would silently produce empty/default content.
        """
        from pathlib import Path as P
        # Load engine types needed by workflow.py (same approach as test_workflow_definitions.py)
        scripts_dir = P(__file__).resolve().parent.parent.parent / "memento-workflow" / "scripts"
        types_ns: dict = {"__name__": "types", "__annotations__": {}}
        exec(compile((scripts_dir / "types.py").read_text(), str(scripts_dir / "types.py"), "exec"), types_ns)

        wf_path = P(__file__).resolve().parent.parent / "static" / "workflows" / "create-protocol" / "workflow.py"
        wf_ns: dict = {"__name__": "create_protocol", "__file__": str(wf_path), "__annotations__": {}}
        wf_ns.update({k: v for k, v in types_ns.items() if not k.startswith("_")})
        exec(compile(wf_path.read_text(), str(wf_path), "exec"), wf_ns)

        # Build a ProtocolPlan instance from Pydantic models and serialize to dict
        TaskItem = wf_ns["TaskItem"]
        Task = wf_ns["Task"]
        StepDef = wf_ns["StepDef"]
        GroupDef = wf_ns["GroupDef"]
        ItemWrapper = wf_ns["ItemWrapper"]
        ProtocolPlan = wf_ns["ProtocolPlan"]

        plan = ProtocolPlan(
            name="Test",
            context="Context.",
            decision="Decision.",
            rationale="Rationale.",
            consequences_positive=["Good"],
            consequences_negative=["Bad"],
            items=[
                ItemWrapper(type="step", step=StepDef(
                    name="Step One",
                    objective="Do something.",
                    tasks=[Task(heading="Work", subtasks=[TaskItem(title="Item")])],
                    constraints=["Must work"],
                    verification=["pytest"],
                    estimate="1h",
                )),
                ItemWrapper(type="group", group=GroupDef(
                    title="Group",
                    steps=[StepDef(
                        name="Inner",
                        objective="Inner work.",
                        tasks=[Task(heading="Build", subtasks=[TaskItem(title="Sub")])],
                        constraints=[],
                        verification=[],
                        estimate="2h",
                    )],
                )),
            ],
        )

        # Serialize and render — should not crash and should produce correct content
        protocol_dict = json.loads(plan.model_dump_json())
        result = render_protocol(protocol_dict, "/tmp/schema-drift-test", today="2026-03-19")
        assert result["step_count"] == 2

        # Verify content flowed through (not silently empty)
        import shutil
        out = P("/tmp/schema-drift-test")
        try:
            step_content = (out / "01-step-one.md").read_text()
            assert "Do something." in step_content
            assert "Must work" in step_content
            assert "### Work" in step_content
            assert "- [ ] Item" in step_content

            inner_content = (out / "02-group" / "01-inner.md").read_text()
            assert "Inner work." in inner_content
            assert "### Build" in inner_content
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_cli_render(self, tmp_path):
        """CLI render-protocol produces valid output."""
        proto = self._make_protocol()
        json_path = tmp_path / "input.json"
        json_path.write_text(json.dumps(proto), encoding="utf-8")

        out_dir = tmp_path / "output"

        # Import and call CLI function directly
        import subprocess
        result = subprocess.run(
            ["python", str(PROTOCOL_MD_PATH), "render-protocol", str(json_path), str(out_dir), "--today", "2026-03-19"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["step_count"] == 4
        assert (out_dir / "plan.md").is_file()
