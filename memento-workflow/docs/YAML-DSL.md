# Workflow YAML DSL

YAML alternative to `workflow.py` for defining workflows. The compiler translates `workflow.yaml` into the same `WorkflowDef` Python types the engine uses — runtime behavior is identical.

**When to use YAML**: readable, low-noise definitions without Python imports or constructor boilerplate. ~45% shorter than equivalent Python.

**When to use Python**: dynamic construction, programmatic conditions with side effects (`Path.exists()`, arithmetic), complex output schemas with validators.

---

## Quick Start

Create `workflow.yaml` in your workflow directory:

```yaml
name: my-workflow
description: A custom workflow

blocks:
  - shell: detect
    command: "echo detecting"
    result_var: detection

  - prompt: mode
    prompt_type: choice
    message: "Choose analysis mode:"
    options: [quick, thorough]
    default: quick
    result_var: mode

  - llm: analyze
    prompt: analyze.md
    tools: [Read, Glob]

  - group: implement
    when: 'variables.mode == "thorough"'
    isolation: subagent
    model: sonnet
    context_hint: "project structure and coding patterns"
    blocks:
      - llm: code
        prompt: code.md
        tools: [Read, Write, Edit]
      - shell: test
        command: "uv run pytest"
```

The engine discovers `workflow.yaml` automatically (preferred over `workflow.py` if both exist).

---

## Block Types

Each block is a YAML dict. The **first key** determines the block type, its value is the block name.

### Common fields (all block types)

| Field          | Type   | Default  | Description                                                                   |
| -------------- | ------ | -------- | ----------------------------------------------------------------------------- |
| `when`         | string | —        | Inline condition expression (see [Expression Language](#expression-language)) |
| `when_fn`      | string | —        | Python function ref: `module.function` (mutually exclusive with `when`)       |
| `key`          | string | = name   | Stable identity for exec_key, caching, resume. Supports `{{template}}`        |
| `isolation`    | string | `inline` | `inline` or `subagent`                                                        |
| `context_hint` | string | —        | Guides relay agent on what context to summarize for subagent launches         |

### `shell` — subprocess execution

```yaml
- shell: build
  command: "npm run build" # inline command (supports {{template}})
  result_var: build_result # parse stdout JSON → ctx.variables
```

```yaml
- shell: check
  script: scripts/check.sh # path relative to workflow dir
  args: "--flag {{variables.x}}" # appended to script invocation
  env: # env vars passed to subprocess
    API_KEY: "{{variables.api_key}}"
```

| Field        | Type   | Default | Description                                                       |
| ------------ | ------ | ------- | ----------------------------------------------------------------- |
| `command`    | string | —       | Shell command with `{{template}}` substitution                    |
| `script`     | string | —       | Path relative to workflow dir (mutually exclusive with `command`) |
| `args`       | string | `""`    | Args template, appended to script invocation                      |
| `env`        | map    | `{}`    | Env vars with `{{template}}` substitution                         |
| `result_var` | string | `""`    | Parse stdout JSON into `ctx.variables[result_var]`                |

`command` and `script` are mutually exclusive. Scripts are resolved to absolute paths at runtime using `workflow_dir`. The interpreter is chosen by extension: `.py` → `python3`, everything else → `bash`.

### `prompt` — interactive user checkpoint

```yaml
- prompt: choose-mode
  prompt_type: choice
  message: "Choose analysis mode:"
  options: [quick, thorough]
  default: quick
  result_var: mode
```

| Field         | Type   | Default      | Description                                          |
| ------------- | ------ | ------------ | ---------------------------------------------------- |
| `prompt_type` | string | **required** | `choice`, `confirm`, or `input`                      |
| `message`     | string | **required** | Question text with `{{template}}` substitution       |
| `options`     | list   | `[]`         | Available choices (for `choice` type)                |
| `default`     | string | —            | Default answer                                       |
| `result_var`  | string | `""`         | Store answer in `ctx.variables[result_var]`          |
| `strict`      | bool   | `true`       | Enforce exact option match; `false` allows free-text |

### `llm` — LLM prompt step

```yaml
- llm: classify
  prompt: classify.md # file in prompts/ dir
  model: haiku
  tools: [Read, Glob]
  output_schema: schemas.ClassifyOutput
```

```yaml
- llm: quick-check
  prompt_text: | # inline text (mutually exclusive with prompt)
    Analyze {{variables.item}} and summarize findings.
  isolation: subagent
  context_hint: "project files"
```

| Field           | Type   | Default | Description                                                                          |
| --------------- | ------ | ------- | ------------------------------------------------------------------------------------ |
| `prompt`        | string | —       | Prompt file path relative to `prompts/` dir                                          |
| `prompt_text`   | string | —       | Inline prompt text (mutually exclusive with `prompt`)                                |
| `model`         | string | —       | Model override: `haiku`, `sonnet`, `opus`                                            |
| `tools`         | list   | `[]`    | Tools available to the LLM                                                           |
| `output_schema` | string | —       | Pydantic model ref: `module.ClassName` (see [Module Resolution](#module-resolution)) |

With `isolation: subagent`: launches as a single-task Agent (no relay loop, no child_run_id).

### `group` — sequential composition

```yaml
- group: develop
  isolation: subagent
  context_hint: "detection results, current mode"
  model: sonnet
  blocks:
    - llm: plan
      prompt: plan.md
    - llm: implement
      prompt: implement.md
      tools: [Read, Write, Edit]
    - shell: test
      command: "uv run pytest"
```

| Field    | Type   | Default | Description                                  |
| -------- | ------ | ------- | -------------------------------------------- |
| `blocks` | list   | `[]`    | Ordered list of child blocks                 |
| `model`  | string | —       | Default model for LLM steps inside the group |

With `isolation: subagent`: launches relay-based child run with shared context across blocks.

### `loop` — iterate over list

```yaml
- loop: process-items
  over: results.detect.structured_output.items
  as: scan_item
  blocks:
    - shell: process
      command: "echo {{variables.scan_item}}"
```

| Field    | Type   | Default      | Description                            |
| -------- | ------ | ------------ | -------------------------------------- |
| `over`   | string | **required** | Dotpath resolving to a list in context |
| `as`     | string | **required** | Variable name for current item         |
| `blocks` | list   | `[]`         | Blocks to execute per iteration        |

### `retry` — repeat until condition

```yaml
- retry: stabilize
  max_attempts: 5
  until: 'results.flaky-cmd.status == "success"'
  blocks:
    - shell: flaky-cmd
      command: "npm test"
```

```yaml
- retry: stabilize
  max_attempts: 3
  until_fn: conditions.tests_pass # Python ref (mutually exclusive with until)
  blocks:
    - shell: run-tests
      command: "uv run pytest"
```

| Field          | Type   | Default | Description                                           |
| -------------- | ------ | ------- | ----------------------------------------------------- |
| `max_attempts` | int    | `3`     | Maximum retry attempts                                |
| `until`        | string | —       | Condition expression: stop when true                  |
| `until_fn`     | string | —       | Python function ref (mutually exclusive with `until`) |
| `blocks`       | list   | `[]`    | Blocks to retry                                       |

### `conditional` — multi-way branching

```yaml
- conditional: choose-path
  branches:
    - when: 'variables.action == "Delete"'
      blocks:
        - shell: delete
          command: "rm -rf dist/"
    - when: 'variables.action == "Build"'
      blocks:
        - shell: build
          command: "npm run build"
  default:
    - shell: fallback
      command: "echo no match"
```

| Field      | Type | Default | Description                                                 |
| ---------- | ---- | ------- | ----------------------------------------------------------- |
| `branches` | list | `[]`    | Ordered list of `{when/when_fn, blocks}` — first match wins |
| `default`  | list | `[]`    | Blocks if no branch matches                                 |

The `conditional` block itself also supports `when`/`when_fn` as a gate (from common fields).

### `subworkflow` — invoke another workflow

```yaml
- subworkflow: call-helper
  workflow: test-helper
  inject:
    helper_input: "{{results.detect.structured_output.count}}"
```

| Field      | Type   | Default      | Description                                         |
| ---------- | ------ | ------------ | --------------------------------------------------- |
| `workflow` | string | **required** | Target workflow name from registry                  |
| `inject`   | map    | `{}`         | Variables to inject (values support `{{template}}`) |

### `parallel` — concurrent execution per item

```yaml
- parallel: review-files
  for: results.detect.structured_output.items
  as: file
  max_concurrency: 4
  model: sonnet
  template:
    - llm: review
      prompt: review.md
      tools: [Read]
```

| Field             | Type   | Default      | Description                                          |
| ----------------- | ------ | ------------ | ---------------------------------------------------- |
| `for`             | string | **required** | Dotpath resolving to list                            |
| `as`              | string | `item`       | Variable name for current item                       |
| `max_concurrency` | int    | —            | Max parallel lanes                                   |
| `model`           | string | —            | Default model for LLM steps in lanes                 |
| `template`        | list   | `[]`         | Blocks to execute per item (each lane is a subagent) |

---

## Expression Language

Used in `when:` and `until:` fields. Compiled to Python lambdas at load time.

### Grammar

```
expr     = or_expr
or_expr  = and_expr ("or" and_expr)*
and_expr = unary ("and" unary)*
unary    = "not" unary | primary
primary  = "(" expr ")" | dotpath ("??" value)? (("==" | "!=") value | "in" "[" value ("," value)* "]")?
dotpath  = segment ("." segment)*
segment  = [a-zA-Z_][a-zA-Z0-9_-]*
value    = "string" | 'string' | number | true | false | null
```

### Semantics

- **Dotpath** resolves via `ctx.get_var()` — missing paths return `None`
- **Bare dotpath** without operator → truthy check (`bool(resolved)`)
- **`??`** = null coalescing: `variables.x ?? "default"` → use `"default"` if resolved is `None`
- **`== null` / `!= null`** — explicit null checks
- **`in [...]`** with `None` LHS → `False`
- Hyphenated segments supported: `results.risky-step.status`

### Examples

```yaml
# Equality
when: 'results.mode.output == "thorough"'

# Default + equality
when: 'variables.confirmed ?? "yes" == "yes"'

# Membership
when: 'variables.action in ["Full regeneration", "All updates"]'

# Negated truthy
when: 'not variables.fast_track'

# Boolean combination
when: 'variables.enable_llm == true or results.mode.output == "thorough"'

# Null check
when: 'results.detect.output != null'

# Parenthesized
when: '(variables.a == "x" or variables.b == "y") and not variables.skip'
```

### Limitations

Use `when_fn` / `until_fn` for anything the expression language doesn't cover:

- `Path(...).exists()`, filesystem checks
- Arithmetic comparisons (`>`, `<`, `>=`)
- String operations (`.startswith()`, `.contains()`)
- Any side-effectful logic

---

## Module Resolution

YAML workflows can reference Python objects from companion `.py` files in the same directory. The compiler loads all `.py` files (except `workflow.py`) into isolated namespaces.

### Directory structure

```
my-workflow/
├── workflow.yaml        # workflow definition
├── conditions.py        # condition functions for when_fn / until_fn
├── schemas.py           # Pydantic models for output_schema
├── prompts/
│   ├── classify.md
│   └── implement.md
└── scripts/
    └── check.sh
```

### Referencing functions (`when_fn`, `until_fn`)

```python
# conditions.py
def is_thorough(ctx):
    return ctx.variables.get("mode") == "thorough"

def tests_pass(ctx):
    r = ctx.results.get("run-tests")
    return r is not None and r.status == "success"
```

```yaml
- llm: deep-analysis
  prompt: deep.md
  when_fn: conditions.is_thorough

- retry: stabilize
  max_attempts: 5
  until_fn: conditions.tests_pass
  blocks:
    - shell: run-tests
      command: "uv run pytest"
```

### Referencing schemas (`output_schema`)

```python
# schemas.py
from pydantic import BaseModel

class ClassifyOutput(BaseModel):
    category: str
    confidence: float
```

```yaml
- llm: classify
  prompt: classify.md
  output_schema: schemas.ClassifyOutput
```

The format is always `module_name.attribute_name`, where `module_name` is the `.py` filename without extension.

**Security note**: companion `.py` files are loaded via `exec()` at workflow load time. YAML workflows are trusted code (same as `workflow.py`) — helper modules can execute arbitrary Python at load time. Only use workflows from trusted sources.

---

## Template Substitution

Text fields (`command`, `args`, `env` values, `message`, `options`, `prompt_text`, `key`, `inject` values) support `{{template}}` substitution at runtime, resolved against the workflow context. Structural fields (`model`, `prompt_type`, `isolation`) are not substituted.

| Pattern                                    | Resolves to                                 |
| ------------------------------------------ | ------------------------------------------- |
| `{{variables.name}}`                       | `ctx.variables["name"]`                     |
| `{{results.step.output}}`                  | `ctx.results["step"].output`                |
| `{{results.step.structured_output.field}}` | Nested field from structured output         |
| `{{variables.workflow_dir}}`               | Absolute path to workflow package directory |

---

## YAML vs Python Comparison

**Python** (`workflow.py`):

```python
from pydantic import BaseModel

class Mode(BaseModel):
    output: str

WORKFLOW = WorkflowDef(
    name="example",
    description="Demo",
    blocks=[
        ShellStep(
            name="detect",
            command="echo hello",
            result_var="detection",
        ),
        PromptStep(
            name="mode",
            prompt_type="choice",
            message="Choose mode:",
            options=["quick", "thorough"],
            result_var="mode",
        ),
        LLMStep(
            name="analyze",
            prompt="analyze.md",
            tools=["Read", "Glob"],
            output_schema=Mode,
            condition=lambda ctx:
                ctx.variables.get("mode")
                == "thorough",
        ),
    ],
)
```

**YAML** (`workflow.yaml` + `schemas.py`):

```yaml
name: example
description: Demo

blocks:
  - shell: detect
    command: "echo hello"
    result_var: detection

  - prompt: mode
    prompt_type: choice
    message: "Choose mode:"
    options: [quick, thorough]
    result_var: mode

  - llm: analyze
    prompt: analyze.md
    tools: [Read, Glob]
    output_schema: schemas.Mode
    when: 'variables.mode == "thorough"'
```

```python
# schemas.py
from pydantic import BaseModel

class Mode(BaseModel):
    output: str
```

---

## Complete Example

A workflow that detects project structure, asks the user for mode, conditionally runs analysis, and processes items in parallel:

```yaml
name: analyze-project
description: Detect, analyze, and review project files

blocks:
  - shell: detect
    script: scripts/detect.py
    args: "--root {{variables.project_root}}"
    env:
      VERBOSE: "1"
    result_var: detection

  - prompt: mode
    prompt_type: choice
    message: "Found {{results.detect.structured_output.file_count}} files. Choose mode:"
    options: [quick, thorough]
    default: quick
    result_var: mode

  - llm: classify
    prompt: classify.md
    model: haiku
    output_schema: schemas.ClassifyOutput

  - conditional: choose-depth
    branches:
      - when: 'variables.mode == "thorough"'
        blocks:
          - group: deep-analysis
            isolation: subagent
            model: sonnet
            context_hint: "detection results and file list"
            blocks:
              - llm: plan
                prompt: plan.md
                tools: [Read, Glob, Grep]
              - llm: implement
                prompt: implement.md
                tools: [Read, Write, Edit]
              - shell: test
                command: "uv run pytest -x"
    default:
      - llm: quick-scan
        prompt_text: |
          Do a quick scan of {{variables.project_root}}.
          Focus on: {{results.classify.structured_output.category}}
        tools: [Read, Glob]

  - parallel: review-files
    for: results.detect.structured_output.items
    as: review_item
    max_concurrency: 4
    model: sonnet
    template:
      - llm: review
        prompt: review.md
        tools: [Read]

  - retry: validate
    max_attempts: 3
    until: 'results.run-checks.status == "success"'
    blocks:
      - shell: run-checks
        command: "uv run pytest --tb=short"
      - llm: fix
        prompt: fix.md
        tools: [Read, Edit]
        when: 'results.run-checks.status != "success"'
```

With companion files:

```python
# schemas.py
from pydantic import BaseModel

class ClassifyOutput(BaseModel):
    category: str
    items: list[str]
    file_count: int
```

```markdown
<!-- prompts/classify.md -->

Classify the detected project structure.

Detection results:
{{results.detect.output}}
```

---

## Block Patterns & Usage Guide

### Data flow between steps

Every completed step writes a `StepResult` into two stores:

- **`ctx.results_scoped[exec_key]`** — by full hierarchical key (e.g. `loop:implement[i=2]/verify-red`). Canonical, collision-free. Used internally for replay and idempotency.
- **`ctx.results[name]`** — by block name (or `key` if set). This is what you use in templates and conditions: `results.verify-red.status`. **Last-write-wins**: in a loop, each iteration overwrites the previous value.

```
StepResult:
  .output              # string — raw text output
  .structured_output   # dict | None — parsed JSON (from output_schema or shell JSON stdout)
  .status              # "success" | "failure"
  .exec_key            # deterministic scoped key
```

Three ways data flows forward:

**1. `result_var` → `variables`** (shell and prompt steps only)

```yaml
- shell: detect
  command: 'echo ''{"count": 42}'''
  result_var: detection
# → ctx.variables["detection"] = {"count": 42}  (parsed from JSON stdout)

- prompt: mode
  prompt_type: choice
  message: "Choose:"
  options: [quick, thorough]
  result_var: mode
# → ctx.variables["mode"] = "thorough"  (raw string answer)
```

After `result_var`, downstream steps reference via `{{variables.detection.count}}` or `variables.mode` in conditions.

**2. `results.*` in templates**

Any step's output is available via `{{results.step_name.output}}` in prompt files and template fields:

```yaml
- llm: analyze
  prompt: analyze.md
  # In analyze.md: "Previous results: {{results.detect.output}}"

- shell: next
  command: "echo {{results.analyze.output}}"
```

For structured output (from `output_schema`): `{{results.classify.structured_output.category}}`.

**3. `results.*` in conditions**

```yaml
when: 'results.detect.status == "success"'
when: 'results.classify.structured_output.complexity == "complex"'
```

**Rule of thumb**: use `result_var` for simple values you'll check in conditions (`variables.mode == "thorough"`). Use `results.*` for accessing structured data or full output in prompts.

### User interaction patterns

#### Choice — branching on user preference

The most common pattern: ask, store answer, branch on it.

```yaml
- prompt: mode
  prompt_type: choice
  message: "Choose analysis depth:"
  options: [quick, thorough]
  result_var: mode

# Option A: per-step conditions
- llm: deep-scan
  prompt: deep.md
  when: 'variables.mode == "thorough"'

# Option B: conditional block for multi-step branches
- conditional: mode-branch
  branches:
    - when: 'variables.mode == "thorough"'
      blocks:
        - llm: plan
          prompt: plan.md
        - llm: implement
          prompt: implement.md
  default:
    - llm: quick-scan
      prompt: quick.md
```

Use per-step `when` for single steps. Use `conditional` when branches contain multiple steps.

#### Confirm — gatekeeping dangerous operations

`confirm` type accepts only `"yes"` / `"no"` (enforced by strict validation). Answers are **case-sensitive** — `"Yes"` or `"YES"` will trigger the retry-confirm loop. The workflow doesn't stop on "no" — you must handle both outcomes explicitly.

```yaml
- prompt: proceed
  prompt_type: confirm
  message: "This will modify {{variables.file_count}} files. Proceed?"
  result_var: proceed

# Everything after this needs the gate:
- group: do-work
  when: 'variables.proceed == "yes"'
  blocks:
    - llm: implement
      prompt: implement.md
      tools: [Read, Write, Edit]
    - shell: test
      command: "uv run pytest"
```

Without the `when` guard, blocks execute regardless of the answer.

Common mistake — forgetting that `confirm` stores `"yes"`/`"no"` as strings, not booleans:
```yaml
# WRONG: bare truthy check — "no" is also truthy!
when: 'variables.proceed'

# CORRECT: explicit string comparison
when: 'variables.proceed == "yes"'
```

#### Input — open-ended text

```yaml
- prompt: description
  prompt_type: input
  message: "Describe what you want to build:"
  result_var: task_description
  strict: false    # accept any text (default is true)
```

Set `strict: false` when there are no fixed options. With `strict: true` (default) and no `options`, the answer passes through without validation.

#### Non-strict choice — suggestions with free-text

```yaml
- prompt: strategy
  prompt_type: choice
  message: "Choose a strategy:"
  options: [Resume, Merge, Fresh]
  strict: false    # user can also type a custom answer
  result_var: strategy
```

### Isolation: inline vs subagent

Every block runs either in the current context (`inline`) or in an isolated Agent (`subagent`).

**Inline** (default): step runs in the current Claude session. It sees all previous conversation context — files read, patterns noticed, user preferences. Good for steps that build on prior context.

**Subagent**: step launches a new Agent tool — fresh context window, no prior conversation. Good for:
- Large tasks that would overflow the context
- Tasks that need a different model
- Parallel work (parallel lanes are always subagents)

```yaml
# Single LLM step as subagent (one-shot, no relay)
- llm: review
  prompt: review.md
  isolation: subagent
  model: sonnet
  context_hint: "changed files and test results"

# Group as subagent (relay-based, steps share context within the group)
- group: implement
  isolation: subagent
  model: sonnet
  context_hint: "project structure, plan output"
  blocks:
    - llm: code
      prompt: code.md
      tools: [Read, Write, Edit]
    - shell: test
      command: "uv run pytest"
    - llm: review-results
      prompt: review.md
      tools: [Read]
    # All three steps share context inside the subagent
```

`context_hint` tells the relay agent what to summarize from the current conversation and pass to the subagent. Without it, the subagent starts with only the engine's prompt — no project context.

**Limitation**: subagents cannot launch sub-subagents. Inside a subagent, all blocks run inline regardless of their `isolation` setting.

### Shell patterns

#### JSON output → variables

```yaml
- shell: detect
  command: "python3 scripts/detect.py --json"
  result_var: detection
# If stdout is valid JSON, parsed into ctx.variables["detection"]
# Access fields: {{variables.detection.files}}, {{variables.detection.count}}
```

#### External scripts with args and env

```yaml
- shell: analyze
  script: scripts/analyze.py          # relative to workflow dir
  args: "--root {{variables.cwd}} --mode {{variables.mode}}"
  env:
    VERBOSE: "1"
    API_KEY: "{{variables.api_key}}"
  result_var: analysis
```

Scripts are resolved to absolute paths using `workflow_dir`. Do not use `..` path segments — scripts must stay within the workflow directory. Interpreter is chosen by extension: `.py` → `python3`, `.sh` (and everything else) → `bash`. Execution uses `shell=False` with an argv list for safety.

`args` is split via `shlex.split()` — use shell quoting for args with spaces: `args: '--name "John Doe"'`.

#### Checking shell status in conditions

Shell steps that fail (non-zero exit) are recorded with `status: "failure"`. The workflow continues (doesn't abort):

```yaml
- shell: lint
  command: "npm run lint"

- llm: fix-lint
  prompt: fix-lint.md
  when: 'results.lint.status != "success"'
```

### Retry patterns

#### Shell retry (wait for external system)

```yaml
- retry: wait-for-deploy
  max_attempts: 5
  until: 'results.health-check.status == "success"'
  blocks:
    - shell: health-check
      command: "curl -sf https://staging.example.com/health"
```

#### LLM + validation retry (structured output)

```yaml
- retry: generate
  max_attempts: 3
  until: 'results.validate.status == "success"'
  blocks:
    - llm: draft
      prompt: draft.md
      output_schema: schemas.PlanOutput
    - shell: validate
      command: "python3 scripts/validate.py"
```

When `output_schema` validation fails, the step records `status: "failure"`. The retry block re-enters automatically.

#### Red-green TDD cycle

From the development workflow — write tests, verify they fail, implement, verify they pass:

```yaml
- loop: implement
  over: results.plan.structured_output.tasks
  as: unit
  blocks:
    - llm: write-tests
      prompt: write-tests.md
      tools: [Read, Write, Edit, Glob, Grep]

    - llm: verify-red
      prompt: verify-red.md
      tools: [Bash, Read]
      model: haiku
      output_schema: schemas.TestStatus

    - llm: implement
      prompt: implement.md
      tools: [Read, Write, Edit, Bash, Glob, Grep]

    - retry: green-loop
      max_attempts: 3
      until_fn: conditions.tests_green
      blocks:
        - llm: verify-green
          prompt: verify-green.md
          tools: [Bash, Read]
          model: haiku
          output_schema: schemas.TestStatus
        - llm: fix
          prompt: fix.md
          tools: [Read, Write, Edit, Bash]
          when: 'results.verify-green.structured_output.status != "green"'
```

### Parallel patterns

#### Parallel reviews by competency

```yaml
# Step 1: determine what to review
- llm: scope
  prompt: scope.md
  model: haiku
  output_schema: schemas.ReviewScope

# Step 2: parallel reviews — one lane per competency
- parallel: reviews
  for: results.scope.structured_output.competencies
  as: competency
  max_concurrency: 4
  model: sonnet
  template:
    - llm: review
      prompt: review.md
      tools: [Read, Grep, Glob]

# Step 3: synthesize all reviews
- llm: synthesize
  prompt: synthesize.md
  output_schema: schemas.ReviewFindings
```

Each parallel lane is a subagent automatically. The template blocks share context within a lane (like a group with `isolation: subagent`).

**Note**: inside a child run (subagent), `parallel` is downgraded to sequential execution (the engine logs a warning). Nested parallelism is not supported.

### Composing workflows

#### SubWorkflow — reuse across workflows

```yaml
# In development/workflow.yaml:
- subworkflow: review
  workflow: code-review
  when: 'variables.mode != "protocol"'

# In code-review/workflow.yaml (discovered separately):
name: code-review
description: Parallel competency review
blocks:
  - llm: scope
    ...
```

The sub-workflow gets a copy of the parent's context (results, variables). `inject` overrides specific variables:

```yaml
- subworkflow: call-helper
  workflow: helper
  inject:
    target_dir: "{{variables.src_dir}}"
    mode: "strict"
```

#### Group as inline composition

When you don't need isolation but want logical grouping (e.g., for a shared `when` condition):

```yaml
- group: optional-extras
  when: 'variables.mode == "thorough"'
  blocks:
    - llm: deep-analysis
      prompt: deep.md
    - shell: coverage
      command: "uv run pytest --cov"
    - llm: coverage-report
      prompt: coverage.md
```

All three steps share the current context and only run if mode is "thorough".

### Prompt file vs inline prompt

**Prompt file** (`prompt:`) — for substantial prompts with instructions, templates, structure:

```yaml
- llm: classify
  prompt: classify.md    # in prompts/ dir
```

**Inline prompt** (`prompt_text:`) — for simple, context-dependent prompts:

```yaml
- llm: summarize
  prompt_text: |
    Summarize the analysis results for {{variables.project_name}}.
    Key findings: {{results.analyze.output}}
    Be concise — 3 bullet points max.
```

They are mutually exclusive. Prompt files support `{{template}}` substitution the same way.
