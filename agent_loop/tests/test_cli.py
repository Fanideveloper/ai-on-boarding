"""The command-line entry point must show the lifecycle and fail cleanly."""

from __future__ import annotations

import agent_loop.__main__ as cli
from agent_loop.loop import Event, UnusableResponse
from agent_loop.tools import ToolResult


def test_the_transcript_shows_each_stop_reason_and_tool_call(capsys):
    cli._show(Event(iteration=1, stop_reason=None))  # a response with no stop reason at all
    cli._show(Event(iteration=1, tool_name="calculator", tool_input={"expression": "6 * 7"},
                    result=ToolResult("42")))
    out = capsys.readouterr().out
    assert "iter 1  stop_reason=None" in out
    assert "calculator(expression='6 * 7')" in out and "42" in out


def test_a_run_that_produces_no_answer_reports_it_rather_than_raising(monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise UnusableResponse("the model stopped with 'max_tokens'")

    monkeypatch.setattr(cli, "run", refuse)
    assert cli.main(["anything"]) == 1
    assert "no answer" in capsys.readouterr().err
