# Development Workflow Architecture

The `/develop` workflow implements a TDD-driven development process with automated verification gates. It supports three execution modes: **normal**, **fast-track** (trivial changes), and **protocol** (orchestrated multi-step work).

## Overview

```mermaid
flowchart TD
    start(["/develop"]) --> classify["Phase 0: Classify<br/><small>sonnet · scope, type, fast_track</small>"]
    classify -.->|"on resume"| resume["resume-context<br/><small>haiku · resume_only</small>"]
    classify --> commands["load-commands<br/><small>shell</small>"]
    resume -.-> commands
    commands --> route{fast_track?}

    route -- "yes" --> ft["Phase 3: Fast Track<br/><small>implement → verify-fix</small>"]
    route -- "no" --> mode{protocol?}

    mode -- "no" --> explore["Phase 1: Explore<br/><small>haiku · subagent</small>"]
    explore --> plan["Phase 2: Plan<br/><small>task breakdown</small>"]
    plan --> tdd[["Phase 3: TDD Loop<br/><small>per task unit</small>"]]

    mode -- "yes" --> ptdd[["Phase 3: Protocol TDD<br/><small>per protocol unit</small>"]]

    tdd --> custom{verification_commands?}
    ptdd --> custom
    ft --> custom

    custom -- "yes" --> vc[["Custom Verification<br/><small>retry max 3</small>"]]
    custom -- "no" --> acc_gate

    vc --> acc_gate{fast_track?}

    acc_gate -- "yes (skip)" --> phase4
    acc_gate -- "no" --> acc[["Acceptance Check<br/><small>retry max 2</small>"]]
    acc --> phase4

    phase4{protocol?}
    phase4 -- "no" --> review[["Phase 4: Code Review<br/><small>parallel competencies</small>"]]
    review --> complete["Phase 5: Complete<br/><small>haiku · summary</small>"]
    phase4 -- "yes" --> proto_complete["Phase 5: Protocol Complete<br/><small>collect-result.py</small>"]

    complete --> done([done])
    proto_complete --> done
```

## Phases

| Phase | Block                                             | Model            | Skip when                  |
| ----- | ------------------------------------------------- | ---------------- | -------------------------- |
| 0     | `classify`                                        | sonnet           | never                      |
| 0r    | `resume-context`                                  | haiku            | fresh run (only on resume) |
| 1     | `explore`                                         | haiku (subagent) | fast_track, protocol       |
| 2     | `plan`                                            | default          | fast_track, protocol       |
| 3     | `implement` / `protocol-implement` / `fast-track` | default          | (mode-dependent)           |
| —     | `verify-custom` + retry                           | shell + default  | no verification_commands   |
| —     | `acceptance-check` + retry                        | sonnet           | fast_track                 |
| 4     | `review` (code-review sub-workflow)               | parallel         | protocol                   |
| 5     | `complete` / `protocol-complete`                  | haiku / shell    | (mode-dependent)           |

---

## TDD Loop (detail)

The workflow iterates over task units from the plan (normal mode) or `variables.units` (protocol mode). Each unit goes through a full RED→GREEN cycle:

```mermaid
flowchart TD
    loop["for each unit"] --> init["init-vars<br/><small>shell · set verify_red = skipped</small>"]
    init --> wt["write-tests<br/><small>LLM · only test files</small>"]
    wt --> skip_vr{type = refactor<br/>OR no test_files?}
    skip_vr -- "no" --> vr["verify-red<br/><small>shell · tests must fail</small>"]
    skip_vr -- "yes (skip verify-red)" --> impl
    vr --> impl["implement<br/><small>LLM · minimal production code</small>"]
    impl --> gloop[["verify-fix<br/><small>sub-workflow</small>"]]
    gloop --> next["next unit"]
```

**write-tests (RED)** — writes failing tests that define expected behavior before any production code:

- Bug fixes: test that reproduces the bug
- Features: tests for the expected API/behavior
- Refactors: verifies existing coverage, adds tests only for gaps

**verify-red** — runs only the unit's test files via `dev-tools.py test --scope specific`. Confirms tests actually fail, catching always-pass assertions. Skipped for refactors (no behavior change) and when no test files are specified.

**implement (GREEN)** — writes minimal production code to make tests pass. Receives `verify_red` output to guide implementation. May fix mechanical test errors (import typos, missing fixtures) but must not change assertion logic.

---

## verify-fix (detail)

Reusable sub-workflow that runs after every implementation step. Retry loop with max 3 attempts:

```mermaid
flowchart TD
    start["verify-fix"] --> loop

    subgraph loop ["retry loop (max 3)"]
        direction TB
        fmt["format<br/><small>shell · auto-format changed files</small>"]
        fmt --> lint["lint<br/><small>shell · changed files only</small>"]
        lint --> test["test<br/><small>shell · full suite</small>"]
        test --> check{lint clean AND<br/>tests green?}
        check -- "no" --> fix["fix<br/><small>LLM · decision tree</small>"]
    end

    check -- "yes" --> done["exit"]
```

- **format** runs first to avoid LLM wasting tokens on formatting
- **lint** scoped to changed files, **test** runs the full suite (catches regressions)
- **fix** LLM receives both lint and test output, uses a decision tree:
    - Mechanical test error (crash before assertion) → fix the test
    - Assertion failure matching task objective → fix production code
    - Assertion failure contradicting task objective → fix the test
- Loop exits early if lint clean + tests green (fix step skipped)

Injects `workdir` and `scope` (backend/frontend/fullstack) to target the right toolchain.

**Used in 4 places**: after TDD implement (`green-loop`), after fast-track (`fast-verify`), inside verify-custom-retry, inside acceptance-retry.

---

## Custom Verification (detail)

Protocol-specific commands (type-check, build, etc.) run after TDD/fast-track completes. Only active when `verification_commands` is set.

```mermaid
flowchart TD
    vc["verify-custom<br/><small>shell · run commands</small>"] --> ok{all pass?}
    ok -- "yes" --> done["exit"]
    ok -- "no" --> fix["fix-verify-custom<br/><small>LLM · fix failures</small>"]
    fix --> vf[["verify-fix<br/><small>lint + test</small>"]]
    vf --> rerun["re-verify-custom<br/><small>shell · rerun commands</small>"]
    rerun --> ok
```

Retry max 3 attempts. The LLM fixes code/config to satisfy failing commands without weakening or removing verification commands (they are acceptance criteria).

---

## Acceptance Check (detail)

After all implementation and verification passes, a sonnet LLM audits the diff against the original task requirements. Skipped for fast-track.

```mermaid
flowchart TD
    ac["acceptance-check<br/><small>sonnet · read-only audit</small>"] --> ok{all requirements<br/>covered?}
    ok -- "yes" --> done["exit"]
    ok -- "no" --> wt["write-acceptance-tests<br/><small>LLM · RED · returns test_files</small>"]
    wt --> run["verify-acceptance-red<br/><small>shell · run specific test files</small>"]
    run --> green{tests green?}
    green -- "no" --> impl["implement-acceptance<br/><small>LLM · GREEN</small>"]
    green -- "yes (skip)" --> vf
    impl --> vf[["verify-fix<br/><small>lint + test</small>"]]
    vf --> recheck["acceptance-check<br/><small>sonnet · re-audit</small>"]
    recheck --> ok
```

Retry max 2 attempts. The audit checks each requirement for both implementation and test coverage. The `implement-acceptance` step is skipped when tests already pass (test-only gap: implementation exists but tests were missing).

---

## Verification Gates

Three layers, each catching different problem classes:

| Gate                 | Type              | Runs after                | Catches                                 | Retry |
| -------------------- | ----------------- | ------------------------- | --------------------------------------- | ----- |
| **verify-fix**       | lint + test       | every implementation step | syntax, lint, regressions               | 3x    |
| **verify-custom**    | protocol commands | TDD/fast-track            | build, type errors, project checks      | 3x    |
| **acceptance-check** | criteria audit    | verify-custom             | missing criteria, untested behavior     | 2x    |

All three must pass for `protocol-complete` to report `passed: true`.

## Output Schemas

| Schema                  | Used by                | Fields                                                               |
| ----------------------- | ---------------------- | -------------------------------------------------------------------- |
| `ClassifyOutput`        | classify               | scope, type, complexity, fast_track, relevant_guides                 |
| `ExploreOutput`         | explore                | files_to_modify, reference_files, existing_tests, patterns, findings |
| `PlanOutput`            | plan                   | tasks (list of PlanTask), findings                                   |
| `AcceptanceOutput`      | acceptance-check       | covered, missing, passed                                             |
| `AcceptanceTestsOutput` | write-acceptance-tests | test_files                                                           |
| `WriteTestsOutput`      | write-tests            | test_files                                                           |
| `DevelopResult`         | complete               | summary, files_changed, findings                                     |

## Key Files

| File                | Purpose                                            |
| ------------------- | -------------------------------------------------- |
| `workflow.py`       | Workflow definition (blocks, schemas, conditions)  |
| `dev-tools.py`      | Shell tool for lint, test, format, verify commands |
| `collect-result.py` | Protocol-mode result aggregation                   |
| `prompts/`          | LLM prompt templates per step                      |
