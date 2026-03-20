---
id: 02-externalize-prompt-text-to-file
status: done
estimate: 2h
---
# Externalize prompt text to file

## Objective

<!-- objective -->
Move prompt text delivery from inline MCP response to file-based. The server already writes `prompt.md` to artifacts for audit — add a `prompt_file` field to `PromptAction` so the relay reads the prompt via Read tool instead of receiving it inline.

This is the highest-impact change: prompts are 10-50KB and currently transmitted inline, then duplicated in the LLM's context window.

Additionally, support `cache_prompt` on LLMStep for template-level hash caching. When enabled, the raw template (before substitution) is cached in `.workflow-state/_prompts/{hash}.md` and reused across steps sharing the same template. Variables are externalized separately to context_files. For code-review with 5 parallel competencies using the same `02-review.md` template — 1 Read instead of 5.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Add prompt_file field to PromptAction

- [ ] Add `prompt_file: str | None` field to `PromptAction` in protocol.py
  Optional field, defaults to None. When set, relay should read prompt from this file path instead of using inline `prompt` field.

- [ ] Set prompt_file in `_build_prompt_action()` in actions.py
  When `state.artifacts_dir` is available (i.e. `write_llm_prompt_artifact` is called), set `prompt_file` to the artifact path. The prompt.md file is already written at line 84 — just capture the path.

  ```python
  prompt_path = write_llm_prompt_artifact(state.artifacts_dir, exec_key, prompt_text)
  # prompt_path = artifacts_dir / artifact_subpath / "prompt.md"
  ```

- [ ] When prompt_file is set, clear inline prompt to a short stub
  Set `prompt` to a short message like `"(see prompt_file)"` instead of the full text. This ensures backward compatibility — old relays see a hint, new relays read the file.

  Do NOT set prompt to empty string — that would break relays that don't understand prompt_file.
<!-- /task -->

<!-- task -->
### Update relay protocol documentation

- [ ] Update prompt handler in workflow-engine SKILL.md
  Add to the `prompt` action handler:

  > If `prompt_file` is present, read the prompt from that file path using the Read tool. The inline `prompt` field contains only a stub when `prompt_file` is set.

- [ ] Add backward compatibility note
  Document that old relays without prompt_file support will see the stub text and should still work (just won't get the full prompt context).
<!-- /task -->

<!-- task -->
### Lower substitute_with_files threshold to 512 chars

- [ ] Change threshold from 1000 to 512 in `substitute_with_files()` (utils.py)
  512 chars is the approximate break-even point where file externalization saves more tokens than the Read tool call overhead (~200 tokens).

- [ ] Update tests that assert threshold behavior
<!-- /task -->

<!-- task -->
### Add cache_prompt support for template-level hash caching

- [ ] Add `cache_prompt: bool = False` field to LLMStep in types.py
  When True, the raw template (before variable substitution) is cached in `.workflow-state/_prompts/{hash}.md`. Variables are externalized to context_files separately.

- [ ] Implement template caching in `_build_prompt_action()` in actions.py
  When `cache_prompt=True`:
  1. Read raw template from file (before `substitute`/`substitute_with_files`)
  2. Hash the raw template → `sha256(raw)[:12]`
  3. Write to `.workflow-state/_prompts/{hash}.md` if not exists
  4. Run `substitute_with_files` on the raw template — variables go to context_files
  5. Set `prompt_file` to the cached template path (not per-step artifact)
  6. Relay reads template once, context_files per step

  ```python
  if step.cache_prompt and state.artifacts_dir:
      raw_hash = hashlib.sha256(raw.encode()).hexdigest()[:12]
      cache_dir = state.artifacts_dir.parent.parent / "_prompts"
      cached = cache_dir / f"{raw_hash}.md"
      if not cached.exists():
          cache_dir.mkdir(exist_ok=True)
          cached.write_text(raw, encoding="utf-8")
      # substitute_with_files still runs — externalizes variables to context_files
      _, context_files = substitute_with_files(raw, state.ctx, step_dir)
      prompt_file = str(cached)
  ```

- [ ] Add `prompt_hash: str | None` field to PromptAction in protocol.py
  Lets the relay skip Read if it already has this template in context (same pattern as `schema_id`).

- [ ] Add tests for cache_prompt
  - Two steps with same template + different variables → same prompt_file path
  - Two steps with different templates → different prompt_file paths
  - context_files contain per-step variable data
<!-- /task -->

<!-- task -->
### Add tests for prompt_file externalization

- [ ] Test that PromptAction includes prompt_file when artifacts_dir is available
  Call `_build_prompt_action` with a state that has `artifacts_dir` set. Verify `prompt_file` points to the written prompt.md and `prompt` is a stub.

- [ ] Test that PromptAction falls back to inline when artifacts_dir is None
  Call `_build_prompt_action` without `artifacts_dir`. Verify `prompt` contains full text and `prompt_file` is None.

- [ ] Test action serialization includes prompt_file
  Verify `action_to_dict()` includes `prompt_file` when set and omits it when None.
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- prompt_file must point to an existing file when set
- Inline prompt field must contain a non-empty stub for backward compatibility
- When artifacts_dir is None, behavior must be identical to current (full inline)
- Existing tests must continue to pass
<!-- /constraints -->

## Implementation Notes

Key insight: `write_llm_prompt_artifact()` already writes the prompt to `{artifacts_dir}/{artifact_path}/prompt.md` (infra/artifacts.py). The path is computed from exec_key via `exec_key_to_artifact_path()`. We just need to return that path and pass it to the PromptAction.

The `action_to_dict()` function already handles `exclude_none=True`, so `prompt_file=None` won't appear in the wire format for fallback cases.

Two modes of prompt externalization:
- **Default** (`cache_prompt=False`): prompt substituted on server, written to per-step artifact, `prompt_file` points to per-step file
- **Cached** (`cache_prompt=True`): raw template hashed and cached in `.workflow-state/_prompts/`, variables externalized to context_files. Relay reads template once per unique hash, context_files per step

Use `cache_prompt=True` on LLMSteps inside `ParallelEachBlock` or `LoopBlock` where the same template runs with different variables.

## Verification

<!-- verification -->
```bash
cd memento-workflow && uv run pytest tests/ -x -q
cd memento-workflow && uv run ruff check scripts/
cd memento-workflow && uv run pyright scripts/engine/protocol.py scripts/engine/actions.py
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento-workflow/scripts/engine/protocol.py
- memento-workflow/scripts/engine/actions.py
- memento-workflow/scripts/infra/artifacts.py
- memento-workflow/skills/workflow-engine/SKILL.md
<!-- /starting_points -->

## Findings


-   [DEFER] Audit workflows for cache_prompt candidates → [.backlog/items/audit-workflows-for-cacheprompt-candidates.md](.backlog/items/audit-workflows-for-cacheprompt-candidates.md)
<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
