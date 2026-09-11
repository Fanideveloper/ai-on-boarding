"""Tests for the loop, written from specs/multi-tool-agent-loop/spec.md."""

from __future__ import annotations

import logging

import pytest

from agent_loop.loop import MAX_ITERATIONS, IterationLimitExceeded, UnusableResponse, run
from agent_loop.tests.conftest import StubClient, finished, requesting, response, text, thinking, tool_use

SEARCH = tool_use("web_search", {"query": "population of Tokyo"}, id="search-1")
CALCULATE = tool_use("calculator", {"expression": "14180000 / 1000"}, id="calc-1")


# --- Requirement: Terminate only on the model's reported stop reason --------------------------


def test_a_response_that_leads_with_text_but_requests_a_tool_continues_the_loop():
    """Neither the first block being text nor final-sounding wording ends a run."""
    client = StubClient(requesting(text("I'm done. All finished!"), SEARCH), finished("14180"))
    assert run("q", client=client, model="m") == "14180"
    assert len(client.requests) == 2


def test_the_loop_returns_the_text_when_the_model_reports_it_has_finished():
    assert run("q", client=StubClient(finished("the answer")), model="m") == "the answer"


# --- Requirement: Thread results back into the conversation -----------------------------------


def test_the_models_response_is_added_to_the_conversation_whole():
    """Reasoning produced alongside a tool request must be returned unchanged."""
    content = [thinking("sig-abc"), text("looking it up"), SEARCH]
    client = StubClient(response("tool_use", *content), finished())
    run("q", client=client, model="m")
    assert client.conversation[1] == {"role": "assistant", "content": content}


def test_every_result_for_one_response_is_returned_in_a_single_turn():
    two = requesting(tool_use("calculator", {"expression": "1 + 1"}, id="a"),
                     tool_use("calculator", {"expression": "2 + 2"}, id="b"))
    client = StubClient(two, finished())
    run("q", client=client, model="m")
    user_turns = [m for m in client.conversation if m["role"] == "user"]
    assert len(user_turns) == 2  # the prompt, then one turn carrying both results
    assert [r["tool_use_id"] for r in user_turns[1]["content"]] == ["a", "b"]


# --- Requirement: Execute every requested tool and return its result --------------------------


def test_a_result_is_returned_against_the_request_it_answers():
    client = StubClient(requesting(CALCULATE), finished())
    run("q", client=client, model="m")
    result = client.conversation[2]["content"][0]
    assert (result["type"], result["tool_use_id"], result["content"], result["is_error"]) == (
        "tool_result", "calc-1", "14180", False)


def test_a_tool_that_cannot_run_returns_an_error_to_the_model_and_the_loop_continues():
    client = StubClient(requesting(tool_use("no_such_tool", {}, id="bad-1")), finished("recovered"))
    assert run("q", client=client, model="m") == "recovered"
    assert client.conversation[2]["content"][0]["is_error"] is True


# --- Requirement: Support several tool calls in sequence / Cap the number of iterations -------


def test_a_value_found_by_one_tool_is_carried_into_the_next_call_well_before_the_cap():
    client = StubClient(requesting(SEARCH), requesting(CALCULATE), finished("14180"))
    assert run("q", client=client, model="m") == "14180"
    assert len(client.requests) == 3 < MAX_ITERATIONS == 20
    assert "14180000" in client.requests[1]["messages"][2]["content"][0]["content"]
    assert client.requests[2]["messages"][4]["content"][0]["content"] == "14180"


def test_reaching_the_safety_cap_records_a_warning_and_cannot_be_received_as_an_answer(caplog):
    client = StubClient(*[requesting(CALCULATE) for _ in range(5)])
    with caplog.at_level(logging.WARNING, logger="agent_loop.loop"):
        with pytest.raises(IterationLimitExceeded):
            run("q", client=client, model="m", max_iterations=5)
    assert len(client.requests) == 5
    assert any("safety cap" in r.message for r in caplog.records if r.levelno == logging.WARNING)


# --- Requirement: Report a response the loop cannot act on ------------------------------------


@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
def test_an_unrecognised_stop_reason_is_reported_rather_than_returned(stop_reason):
    with pytest.raises(UnusableResponse, match=stop_reason):
        run("q", client=StubClient(response(stop_reason, text("partial"))), model="m")


def test_a_tool_request_naming_no_tool_is_reported_and_no_empty_turn_is_sent():
    client = StubClient(response("tool_use", text("I meant to call something")))
    with pytest.raises(UnusableResponse):
        run("q", client=client, model="m")
    assert len(client.requests) == 1
