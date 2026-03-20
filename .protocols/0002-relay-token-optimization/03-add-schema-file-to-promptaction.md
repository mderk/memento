---
id: 03-add-schema-file-to-promptaction
status: pending
estimate: 1.5h
---
# Add schema_file to PromptAction via run-level hash cache

## Objective

<!-- objective -->
Externalize JSON schema delivery to files using a shared hash-based cache in `.workflow-state/_schemas/`. Schemas are written once per unique content hash and reused across all runs. When the same schema appears in multiple LLM steps (e.g. parallel code-review lanes), the relay reads the file once — subsequent steps with the same `schema_id` are already in context.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Implement schema hash cache in .workflow-state/_schemas/

- [ ] Add `schema_file: str | None` and `schema_id: str | None` fields to PromptAction in protocol.py

- [ ] In `_build_prompt_action`, hash schema and write to shared cache
  ```python
  schema = schema_dict(step.output_schema)
  if schema and state.artifacts_dir:
      schema_bytes = json.dumps(schema, sort_keys=True).encode()
      h = hashlib.sha256(schema_bytes).hexdigest()[:12]
      # .workflow-state/_schemas/ — shared across all runs
      cache_dir = state.artifacts_dir.parent.parent / "_schemas"
      schema_path = cache_dir / f"{h}.json"
      if not schema_path.exists():
          cache_dir.mkdir(exist_ok=True)
          schema_path.write_text(json.dumps(schema, indent=2))
      action.schema_file = str(schema_path)
      action.schema_id = h
      action.json_schema = None  # relay reads from file
  ```

- [ ] Clear inline `json_schema` when `schema_file` is set
<!-- /task -->

<!-- task -->
### Update relay protocol and add tests

- [ ] Update prompt handler in SKILL.md for schema_file + schema_id
  If `schema_file` is present, check if `schema_id` was already read in this conversation. If yes — schema is in context, skip Read. If no — Read the file.

- [ ] Add tests for schema hash cache
  - Same schema used in two steps → same file path
  - Different schemas → different file paths
  - Schema file content matches original json_schema

- [ ] Test that schema cache dir is `.workflow-state/_schemas/` not per-run
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- schema_file must contain valid JSON matching the original json_schema
- Same schema content → same hash → same file path (deterministic)
- Cache is shared across runs — files persist until cleanup
- When artifacts_dir is None, keep inline json_schema (no cache available)
<!-- /constraints -->

## Implementation Notes

Schema is computed via `schema_dict(step.output_schema)` in `_build_prompt_action`. `sort_keys=True` in json.dumps ensures deterministic hashing regardless of dict ordering.

The `schema_id` field lets the relay skip redundant Reads: if it already read schema `a1b2c3d4e5f6` earlier in the conversation, it doesn't need to read again — the schema is in context.

Cache lives at `.workflow-state/_schemas/` — parent of all run dirs. Cleanup skill should preserve this directory.

## Verification

<!-- verification -->
```bash
cd memento-workflow && uv run pytest tests/ -x -q
cd memento-workflow && uv run ruff check scripts/
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento-workflow/scripts/engine/protocol.py
- memento-workflow/scripts/engine/actions.py
- memento-workflow/scripts/utils.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
