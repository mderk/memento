"""YAML workflow compiler.

Translates workflow.yaml → WorkflowDef (the same Python types the engine uses).
Three components: expression parser, block compiler, module resolver.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable, cast

import yaml

from .types import (
    Block,
    Branch,
    ConditionalBlock,
    GroupBlock,
    LLMStep,
    LoopBlock,
    ParallelEachBlock,
    PromptStep,
    RetryBlock,
    ShellStep,
    SubWorkflow,
    WorkflowContext,
    WorkflowDef,
)

logger = logging.getLogger("workflow-engine")


# ---------------------------------------------------------------------------
# A. Expression parser — tokenizer + recursive descent → lambda
# ---------------------------------------------------------------------------

# Token types
_TOK_DOT = "DOT"
_TOK_LPAREN = "LPAREN"
_TOK_RPAREN = "RPAREN"
_TOK_LBRACKET = "LBRACKET"
_TOK_RBRACKET = "RBRACKET"
_TOK_COMMA = "COMMA"
_TOK_EQ = "EQ"
_TOK_NEQ = "NEQ"
_TOK_COALESCE = "COALESCE"
_TOK_AND = "AND"
_TOK_OR = "OR"
_TOK_NOT = "NOT"
_TOK_IN = "IN"
_TOK_STRING = "STRING"
_TOK_NUMBER = "NUMBER"
_TOK_TRUE = "TRUE"
_TOK_FALSE = "FALSE"
_TOK_NULL = "NULL"
_TOK_IDENT = "IDENT"
_TOK_EOF = "EOF"

_TOKEN_RE = re.compile(
    r"""
    \s*(?:
        (?P<eq>==)
      | (?P<neq>!=)
      | (?P<coalesce>\?\?)
      | (?P<lparen>\()
      | (?P<rparen>\))
      | (?P<lbracket>\[)
      | (?P<rbracket>\])
      | (?P<comma>,)
      | (?P<dot>\.)
      | (?P<dq_string>"[^"]*")
      | (?P<sq_string>'[^']*')
      | (?P<number>-?\d+(?:\.\d+)?)
      | (?P<ident>[a-zA-Z_][a-zA-Z0-9_-]*)
    )
    """,
    re.VERBOSE,
)

_KEYWORDS = {"and": _TOK_AND, "or": _TOK_OR, "not": _TOK_NOT, "in": _TOK_IN,
              "true": _TOK_TRUE, "false": _TOK_FALSE, "null": _TOK_NULL}


def _tokenize(expr: str) -> list[tuple[str, Any]]:
    """Tokenize an expression string into (type, value) pairs."""
    tokens: list[tuple[str, Any]] = []
    pos = 0
    while pos < len(expr):
        # Skip whitespace
        while pos < len(expr) and expr[pos] in " \t\n\r":
            pos += 1
        if pos >= len(expr):
            break
        m = _TOKEN_RE.match(expr, pos)
        if not m:
            raise SyntaxError(f"Unexpected character at position {pos}: {expr[pos:]!r}")
        pos = m.end()
        if m.group("eq"):
            tokens.append((_TOK_EQ, "=="))
        elif m.group("neq"):
            tokens.append((_TOK_NEQ, "!="))
        elif m.group("coalesce"):
            tokens.append((_TOK_COALESCE, "??"))
        elif m.group("lparen"):
            tokens.append((_TOK_LPAREN, "("))
        elif m.group("rparen"):
            tokens.append((_TOK_RPAREN, ")"))
        elif m.group("lbracket"):
            tokens.append((_TOK_LBRACKET, "["))
        elif m.group("rbracket"):
            tokens.append((_TOK_RBRACKET, "]"))
        elif m.group("comma"):
            tokens.append((_TOK_COMMA, ","))
        elif m.group("dot"):
            tokens.append((_TOK_DOT, "."))
        elif m.group("dq_string"):
            tokens.append((_TOK_STRING, m.group("dq_string")[1:-1]))
        elif m.group("sq_string"):
            tokens.append((_TOK_STRING, m.group("sq_string")[1:-1]))
        elif m.group("number"):
            txt = m.group("number")
            tokens.append((_TOK_NUMBER, float(txt) if "." in txt else int(txt)))
        elif m.group("ident"):
            word = m.group("ident")
            kw = _KEYWORDS.get(word)
            if kw:
                tokens.append((kw, word))
            else:
                tokens.append((_TOK_IDENT, word))
    tokens.append((_TOK_EOF, None))
    return tokens


class _Parser:
    """Recursive descent parser for condition expressions."""

    def __init__(self, tokens: list[tuple[str, Any]], source: str) -> None:
        self.tokens = tokens
        self.pos = 0
        self.source = source

    def _peek(self) -> tuple[str, Any]:
        return self.tokens[self.pos]

    def _advance(self) -> tuple[str, Any]:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, tok_type: str) -> tuple[str, Any]:
        tok = self._advance()
        if tok[0] != tok_type:
            raise SyntaxError(
                f"Expected {tok_type}, got {tok[0]} ({tok[1]!r}) in expression: {self.source}"
            )
        return tok

    def parse(self) -> Callable[[WorkflowContext], bool]:
        """Parse a full expression and return a condition lambda."""
        node = self._or_expr()
        if self._peek()[0] != _TOK_EOF:
            raise SyntaxError(
                f"Unexpected token {self._peek()!r} after expression in: {self.source}"
            )
        return lambda ctx, _n=node: bool(_n(ctx))

    def _or_expr(self) -> Callable[[WorkflowContext], Any]:
        left = self._and_expr()
        while self._peek()[0] == _TOK_OR:
            self._advance()
            right = self._and_expr()
            left = _make_or(left, right)
        return left

    def _and_expr(self) -> Callable[[WorkflowContext], Any]:
        left = self._unary()
        while self._peek()[0] == _TOK_AND:
            self._advance()
            right = self._unary()
            left = _make_and(left, right)
        return left

    def _unary(self) -> Callable[[WorkflowContext], Any]:
        if self._peek()[0] == _TOK_NOT:
            self._advance()
            operand = self._unary()
            return lambda ctx, _o=operand: not _o(ctx)
        return self._primary()

    def _primary(self) -> Callable[[WorkflowContext], Any]:
        tok_type, tok_val = self._peek()

        # Parenthesized expression
        if tok_type == _TOK_LPAREN:
            self._advance()
            node = self._or_expr()
            self._expect(_TOK_RPAREN)
            return self._postfix(node)

        # Dotpath (starts with IDENT)
        if tok_type == _TOK_IDENT:
            dotpath = self._dotpath()
            def _resolve(ctx: WorkflowContext, _dp: str = dotpath) -> Any:
                return ctx.get_var(_dp)

            resolver: Callable[[WorkflowContext], Any] = _resolve

            # Null coalesce: ??
            if self._peek()[0] == _TOK_COALESCE:
                self._advance()
                default_val = self._value()
                resolver = _make_coalesce(resolver, default_val)

            return self._postfix(resolver)

        raise SyntaxError(
            f"Unexpected token {tok_type} ({tok_val!r}) in expression: {self.source}"
        )

    def _postfix(self, node: Callable[[WorkflowContext], Any]) -> Callable[[WorkflowContext], Any]:
        """Handle comparison operators after a primary/coalesced value."""
        tok_type = self._peek()[0]

        if tok_type == _TOK_EQ:
            self._advance()
            rhs = self._value()
            return lambda ctx, _l=node, _r=rhs: _l(ctx) == _r

        if tok_type == _TOK_NEQ:
            self._advance()
            rhs = self._value()
            return lambda ctx, _l=node, _r=rhs: _l(ctx) != _r

        if tok_type == _TOK_IN:
            self._advance()
            values = self._value_list()
            return lambda ctx, _l=node, _vs=values: _l(ctx) in _vs

        # Bare dotpath → truthy check
        return node

    def _dotpath(self) -> str:
        """Parse a dotpath: segment.segment.segment"""
        _, first = self._expect(_TOK_IDENT)
        parts = [first]
        while self._peek()[0] == _TOK_DOT:
            self._advance()
            _, segment = self._expect(_TOK_IDENT)
            parts.append(segment)
        return ".".join(parts)

    def _value(self) -> Any:
        """Parse a literal value: string, number, true, false, null."""
        tok_type, tok_val = self._advance()
        if tok_type == _TOK_STRING:
            return tok_val
        if tok_type == _TOK_NUMBER:
            return tok_val
        if tok_type == _TOK_TRUE:
            return True
        if tok_type == _TOK_FALSE:
            return False
        if tok_type == _TOK_NULL:
            return None
        raise SyntaxError(
            f"Expected value, got {tok_type} ({tok_val!r}) in expression: {self.source}"
        )

    def _value_list(self) -> list[Any]:
        """Parse [value, value, ...]."""
        self._expect(_TOK_LBRACKET)
        values: list[Any] = []
        if self._peek()[0] != _TOK_RBRACKET:
            values.append(self._value())
            while self._peek()[0] == _TOK_COMMA:
                self._advance()
                values.append(self._value())
        self._expect(_TOK_RBRACKET)
        return values


def _make_or(
    left: Callable[[WorkflowContext], Any],
    right: Callable[[WorkflowContext], Any],
) -> Callable[[WorkflowContext], Any]:
    return lambda ctx, _l=left, _r=right: _l(ctx) or _r(ctx)


def _make_and(
    left: Callable[[WorkflowContext], Any],
    right: Callable[[WorkflowContext], Any],
) -> Callable[[WorkflowContext], Any]:
    return lambda ctx, _l=left, _r=right: _l(ctx) and _r(ctx)


def _make_coalesce(
    resolver: Callable[[WorkflowContext], Any],
    default: Any,
) -> Callable[[WorkflowContext], Any]:
    def _coalesce(ctx: WorkflowContext) -> Any:
        val = resolver(ctx)
        return default if val is None else val
    return _coalesce


def compile_expression(expr: str) -> Callable[[WorkflowContext], bool]:
    """Compile a condition expression string to a callable.

    Public entry point for the expression parser.
    """
    tokens = _tokenize(expr)
    parser = _Parser(tokens, expr)
    return parser.parse()


# ---------------------------------------------------------------------------
# B. Module resolver
# ---------------------------------------------------------------------------


def _load_modules(workflow_dir: Path) -> dict[str, dict[str, Any]]:
    """Load .py files next to workflow.yaml into isolated namespaces.

    Returns {"conditions": namespace, "schemas": namespace, ...}.
    Skips workflow.py (that's the Python workflow definition, not a helper module).
    """
    modules: dict[str, dict[str, Any]] = {}
    for py_file in sorted(workflow_dir.glob("*.py")):
        if py_file.name == "workflow.py":
            continue
        mod_name = py_file.stem
        ns: dict[str, Any] = {"__builtins__": __builtins__, "__name__": mod_name}
        code = py_file.read_text(encoding="utf-8")
        exec(compile(code, str(py_file), "exec"), ns)  # noqa: S102
        modules[mod_name] = ns
    return modules


def _resolve_ref(ref: str, modules: dict[str, dict[str, Any]], kind: str) -> Any:
    """Resolve a 'module.name' reference to an object.

    kind is used in error messages (e.g. 'when_fn', 'output_schema').
    """
    parts = ref.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid {kind} reference {ref!r}: expected 'module.name'")
    mod_name, attr_name = parts
    if mod_name not in modules:
        raise ValueError(f"{kind} reference {ref!r}: module '{mod_name}' not found")
    ns = modules[mod_name]
    if attr_name not in ns:
        raise ValueError(f"{kind} reference {ref!r}: '{attr_name}' not found in '{mod_name}'")
    return ns[attr_name]


# ---------------------------------------------------------------------------
# C. Block compiler
# ---------------------------------------------------------------------------

def _normalize_resume_only(value: Any) -> str:
    """Normalize resume_only from YAML: true/True → "true", "once" → "once", else ""."""
    if value is True or value == "true":
        return "true"
    if value == "once":
        return "once"
    return ""


# Recognised YAML first-keys (block type discriminators)
_BLOCK_TYPES = frozenset({
    "shell", "prompt", "llm", "group", "loop",
    "retry", "conditional", "subworkflow", "parallel",
})


def _compile_condition(
    data: dict[str, Any],
    modules: dict[str, dict[str, Any]],
    when_key: str = "when",
    fn_key: str = "when_fn",
) -> Callable[[WorkflowContext], bool] | None:
    """Compile when/when_fn (or until/until_fn) to a callable."""
    expr = data.get(when_key)
    fn_ref = data.get(fn_key)
    if expr and fn_ref:
        raise ValueError(f"Cannot specify both '{when_key}' and '{fn_key}' on block '{data}'")
    if expr:
        return compile_expression(expr)
    if fn_ref:
        fn = _resolve_ref(fn_ref, modules, fn_key)
        if not callable(fn):
            raise ValueError(f"{fn_key} reference '{fn_ref}' is not callable")
        return cast(Callable[[WorkflowContext], bool], fn)
    return None


def _compile_blocks(
    items: list[dict[str, Any]],
    workflow_dir: Path,
    modules: dict[str, dict[str, Any]],
) -> list[Block]:
    """Compile a list of YAML block dicts into Block objects."""
    return [compile_block(item, workflow_dir, modules) for item in items]


def compile_block(
    data: dict[str, Any],
    workflow_dir: Path,
    modules: dict[str, dict[str, Any]],
) -> Block:
    """Compile a single YAML block dict into a Block.

    The first key determines the block type, its value is the block name.
    """
    # The first key determines the block type (per DSL spec).
    # "prompt" is both a block type and a field on llm blocks, so we can't
    # simply scan all keys — we must use position.
    first_key = next(iter(data))
    if first_key not in _BLOCK_TYPES:
        raise ValueError(f"Unknown block type '{first_key}' in: {data}")
    block_type = first_key
    block_name = data[block_type]

    # Common BlockBase fields
    common: dict[str, Any] = {
        "name": block_name,
        "key": data.get("key", ""),
        "isolation": data.get("isolation", "inline"),
        "context_hint": data.get("context_hint", ""),
        "halt": data.get("halt", ""),
        "resume_only": _normalize_resume_only(data.get("resume_only", "")),
    }

    # Compile condition
    cond = _compile_condition(data, modules)
    if cond is not None:
        common["condition"] = cond

    if block_type == "shell":
        command = data.get("command", "")
        script = data.get("script", "")
        if command and script:
            raise ValueError(f"Shell block '{block_name}': cannot specify both 'command' and 'script'")
        raw_env = data.get("env", {})
        env = {str(k): str(v) for k, v in raw_env.items()} if raw_env else {}
        return ShellStep(
            **common,
            command=command,
            script=script,
            args=data.get("args", ""),
            env=env,
            result_var=data.get("result_var", ""),
            stdin=data.get("stdin", ""),
        )

    if block_type == "prompt":
        return PromptStep(
            **common,
            prompt_type=data["prompt_type"],
            message=data["message"],
            options=data.get("options", []),
            default=data.get("default"),
            result_var=data.get("result_var", ""),
            strict=data.get("strict", True),
        )

    if block_type == "llm":
        prompt_file = data.get("prompt", "")
        prompt_text = data.get("prompt_text", "")
        if prompt_file and prompt_text:
            raise ValueError(f"LLM block '{block_name}': cannot specify both 'prompt' and 'prompt_text'")
        output_schema = None
        if data.get("output_schema"):
            output_schema = _resolve_ref(data["output_schema"], modules, "output_schema")
        return LLMStep(
            **common,
            prompt=prompt_file,
            prompt_text=prompt_text,
            tools=data.get("tools", []),
            model=data.get("model"),
            output_schema=output_schema,
        )

    if block_type == "group":
        return GroupBlock(
            **common,
            blocks=_compile_blocks(data.get("blocks", []), workflow_dir, modules),
            model=data.get("model"),
        )

    if block_type == "loop":
        return LoopBlock(
            **common,
            loop_over=data["over"],
            loop_var=data["as"],
            blocks=_compile_blocks(data.get("blocks", []), workflow_dir, modules),
        )

    if block_type == "retry":
        until = _compile_condition(data, modules, "until", "until_fn")
        if until is None:
            raise ValueError(f"Retry block '{block_name}': must specify 'until' or 'until_fn'")
        return RetryBlock(
            **common,
            until=until,
            max_attempts=data.get("max_attempts", 3),
            halt_on_exhaustion=data.get("halt_on_exhaustion", ""),
            blocks=_compile_blocks(data.get("blocks", []), workflow_dir, modules),
        )

    if block_type == "conditional":
        branches: list[Branch] = []
        for branch_data in data.get("branches", []):
            branch_cond = _compile_condition(branch_data, modules)
            if branch_cond is None:
                raise ValueError("Conditional branch must have 'when' or 'when_fn'")
            branches.append(Branch(
                condition=branch_cond,
                blocks=_compile_blocks(branch_data.get("blocks", []), workflow_dir, modules),
            ))
        default_blocks = _compile_blocks(data.get("default", []), workflow_dir, modules)
        return ConditionalBlock(
            **common,
            branches=branches,
            default=default_blocks,
        )

    if block_type == "subworkflow":
        return SubWorkflow(
            **common,
            workflow=data["workflow"],
            inject=data.get("inject", {}),
        )

    if block_type == "parallel":
        return ParallelEachBlock(
            **common,
            parallel_for=data["for"],
            item_var=data.get("as", "item"),
            max_concurrency=data.get("max_concurrency"),
            model=data.get("model"),
            template=_compile_blocks(data.get("template", []), workflow_dir, modules),
        )

    raise ValueError(f"Unhandled block type: {block_type}")  # pragma: no cover


# ---------------------------------------------------------------------------
# D. Entry point
# ---------------------------------------------------------------------------


def compile_workflow(workflow_dir: Path) -> WorkflowDef:
    """Compile a workflow.yaml file into a WorkflowDef.

    Reads workflow.yaml, loads companion .py modules, compiles all blocks.
    """
    yaml_path = workflow_dir / "workflow.yaml"
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    if not isinstance(raw, dict):
        raise ValueError(
            f"{yaml_path}: expected a YAML mapping at top level, got {type(raw).__name__}"
        )

    name = raw.get("name", workflow_dir.name)
    description = raw.get("description", "")
    prompt_dir = str(workflow_dir / "prompts")

    modules = _load_modules(workflow_dir)
    blocks = _compile_blocks(raw.get("blocks", []), workflow_dir, modules)

    return WorkflowDef(
        name=name,
        description=description,
        blocks=blocks,
        prompt_dir=prompt_dir,
        source_path=str(yaml_path),
    )
