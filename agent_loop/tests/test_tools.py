"""Tests for the two tools, written from specs/multi-tool-agent-loop/spec.md."""

from __future__ import annotations

import socket
import time

import pytest

from agent_loop.tools import TOOLS, calculator, dispatch, web_search


def _declaration(name: str) -> dict:
    return next(t for t in TOOLS if t["name"] == name)


# --- Requirement: Offer a calculator tool / Offer a web search tool ---------------------------


@pytest.mark.parametrize(("name", "field"), [("calculator", "expression"), ("web_search", "query")])
def test_each_tool_is_offered_with_a_description_and_its_input_schema(name, field):
    declaration = _declaration(name)
    assert declaration["description"].strip()
    assert declaration["input_schema"]["required"] == [field]
    assert declaration["input_schema"]["properties"][field]["type"] == "string"


def test_an_arithmetic_expression_is_evaluated():
    result = calculator("14180000 / 1000")
    assert result.is_error is False
    assert result.content == "14180"


def test_a_query_returns_a_stub_result_without_touching_the_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("web_search attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert "14180000" in web_search("population of Tokyo").content
    assert web_search("airspeed of an unladen swallow").is_error is False


# --- Requirement: Evaluate expressions without executing arbitrary code -----------------------


@pytest.mark.parametrize(
    "expression",
    ["().__class__", "__import__('os').system('echo pwned')", "[x for x in range(3)]", "'a' * 3"],
)
def test_an_expression_that_is_not_arithmetic_is_refused(expression):
    assert calculator(expression).is_error is True


def test_a_refused_expression_is_never_evaluated(tmp_path):
    """Refusal must happen before evaluation, not by catching the aftermath."""
    marker = tmp_path / "written-by-the-calculator"
    assert calculator(f"open({str(marker)!r}, 'w').write('x')").is_error is True
    assert not marker.exists()


@pytest.mark.parametrize(
    "expression",
    [
        "1 / 0",
        "1e308 * 10",  # no finite value
        "2 +",  # malformed
        "(-8) ** (1 / 3)",  # complex, not real
        "(-8) ** 0.5 // 2",  # a complex intermediate reaching an operator with no complex form
    ],
)
def test_arithmetic_that_cannot_produce_a_real_value_is_refused_rather_than_raising(expression):
    assert calculator(expression).is_error is True


# --- Requirement: Refuse an expression whose result would be too large to compute --------------


@pytest.mark.parametrize("expression", ["2 ** 999999999", "((10 ** 1000) ** 1000) ** 1000"])
def test_a_power_whose_result_would_be_enormous_is_refused_promptly(expression):
    """Refusal must be predicted, not attempted: without the guard this never returns."""
    started = time.monotonic()
    result = calculator(expression)
    assert result.is_error is True
    assert "too large" in result.content
    assert time.monotonic() - started < 1.0


@pytest.mark.parametrize(
    ("expression", "expected"),
    [("2 ** 10", "1024"), ("2 ** -3", "0.125"), ("1 ** 999999999", "1"), ("2 ** 0.5", "1.4142135623730951")],
)
def test_ordinary_arithmetic_is_unaffected_by_the_bound(expression, expected):
    assert calculator(expression).content == expected


# --- Requirement: Execute every requested tool and return its result (dispatch half) -----------


def test_a_requested_tool_runs_with_the_input_the_model_supplied():
    assert dispatch("calculator", {"expression": "6 * 7"}).content == "42"


@pytest.mark.parametrize(
    ("name", "tool_input"),
    [("nonexistent_tool", {"x": 1}), ("calculator", {}), ("calculator", {"expression": 42}), ("calculator", None)],
)
def test_an_unknown_tool_or_unusable_input_reports_an_error_rather_than_raising(name, tool_input):
    assert dispatch(name, tool_input).is_error is True
