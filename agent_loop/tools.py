"""The tools the model can choose between, and the dispatch that runs them.

A tool never raises at the loop's boundary: anything that goes wrong comes back as a
`ToolResult` marked as an error, so the model can read what happened and respond.
"""

from __future__ import annotations

import ast
import math
import operator
from dataclasses import dataclass
from typing import Any, Callable

CALCULATOR = "calculator"
WEB_SEARCH = "web_search"

MAX_RESULT_BITS = 4096
"""Roughly 1,200 decimal digits - far beyond any arithmetic this tool exists to do."""


@dataclass(frozen=True)
class ToolResult:
    content: str
    is_error: bool = False


# The expression is parsed into a syntax tree and walked, never evaluated. Only numbers, the
# arithmetic operators and the grouping the parser already resolved have a branch here; a
# name, attribute, subscript or call is refused before anything runs.

_BINARY = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class _Refused(Exception):
    """The expression contains something the calculator will not evaluate."""


def _refuse_unbounded_power(base: Any, exponent: Any) -> None:
    """`2 ** 999999999` is arithmetic with a finite value; it simply never returns.

    The result's size is predicted from the base's bit length, so nesting is bounded too -
    each level is checked against the value the level below produced. Floats are left to
    the finite check in `calculator`, which already catches their overflow.
    """
    if not (isinstance(base, int) and isinstance(exponent, int)):
        return
    if exponent < 0 or base in (0, 1, -1):
        return
    if base.bit_length() * exponent > MAX_RESULT_BITS:
        raise _Refused(f"a result of about {base.bit_length() * exponent} bits is too large")


def _evaluate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise _Refused(f"{type(node.value).__name__} is not a number")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow):
            _refuse_unbounded_power(left, right)
        return _BINARY[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_evaluate(node.operand))
    raise _Refused(f"{type(node).__name__} is not arithmetic")


def calculator(expression: str) -> ToolResult:
    """Evaluate an arithmetic expression, refusing anything that is not arithmetic."""
    try:
        value = _evaluate(ast.parse(expression, mode="eval").body)
    except SyntaxError as exc:
        return ToolResult(f"error: {expression!r} is not a valid expression ({exc.msg})", True)
    except _Refused as exc:
        return ToolResult(f"error: refused to evaluate {expression!r} - {exc}", True)
    except ZeroDivisionError:
        return ToolResult(f"error: {expression!r} divides by zero", True)
    except (OverflowError, ValueError) as exc:
        return ToolResult(f"error: {expression!r} has no value ({exc})", True)
    except TypeError:
        # A complex intermediate (negative base, fractional power) reaching `//` or `%`.
        return ToolResult(f"error: {expression!r} has no real value", True)

    # A negative base to a fractional power gives a complex number, which skips the finite check.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ToolResult(f"error: {expression!r} has no real value", True)
    if isinstance(value, float) and not math.isfinite(value):
        return ToolResult(f"error: {expression!r} has no finite value", True)
    if isinstance(value, float) and value.is_integer():
        return ToolResult(str(int(value)))
    return ToolResult(str(value))


_STUB_RESULTS = {
    "tokyo": "Tokyo metropolitan population: 14180000 (stub result)",
    "france": "France population: 68400000 (stub result)",
    "london": "Greater London population: 8866000 (stub result)",
}


def web_search(query: str) -> ToolResult:
    """Return a stub result for a query. Nothing here reaches the network."""
    for term, result in _STUB_RESULTS.items():
        if term in query.lower():
            return ToolResult(result)
    return ToolResult(f"No stub result is held for {query!r} (stub result)")


TOOLS: list[dict[str, Any]] = [
    {
        "name": WEB_SEARCH,
        "description": (
            "Search the web for a fact you do not already know, such as a population, a price, "
            "or any current value. Call this before doing arithmetic on a value you were not "
            "given in the question."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What to search for."}},
            "required": ["query"],
        },
    },
    {
        "name": CALCULATOR,
        "description": (
            "Evaluate an arithmetic expression and return its value. Call this whenever a "
            "calculation is needed, rather than working the arithmetic out yourself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "For example '14180000 / 1000'."}
            },
            "required": ["expression"],
        },
    },
]

# Each tool's function, and the name of the single input it reads.
_HANDLERS: dict[str, tuple[Callable[[str], ToolResult], str]] = {
    CALCULATOR: (calculator, "expression"),
    WEB_SEARCH: (web_search, "query"),
}


def dispatch(name: str, tool_input: Any) -> ToolResult:
    """Run the named tool on the model's input, returning an error result rather than raising."""
    if name not in _HANDLERS:
        return ToolResult(f"error: there is no tool named {name!r}", True)
    run, field = _HANDLERS[name]
    value = tool_input.get(field) if isinstance(tool_input, dict) else None
    if not isinstance(value, str) or not value.strip():
        return ToolResult(f"error: {name} needs a non-empty {field!r} string", True)
    try:
        return run(value)
    except Exception as exc:  # a tool must never end the run by raising
        return ToolResult(f"error: {name} failed ({type(exc).__name__}: {exc})", True)
