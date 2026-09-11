"""The agent loop: ask, execute what the model asks for, feed the result back, ask again.

The loop ends when the model says it has ended, and at no other time - not when the
response *looks* finished by its shape or wording, and not after a number of turns.
Every stop reason is accounted for: the two the loop can act on are handled, and any
other stops the run and says what it was, because a response the loop cannot act on
is not an answer and must not be returned as one.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from agent_loop.tools import TOOLS, ToolResult, dispatch

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 20
"""A safeguard against a run that cannot finish - never how a normal run ends."""

DEFAULT_MODEL = "claude-haiku-4-5"
MODEL_VARIABLE = "AGENT_LOOP_MODEL"
MAX_TOKENS = 2048

REQUESTING_A_TOOL = "tool_use"
FINISHED = "end_turn"


class AgentLoopError(Exception):
    """The run did not produce an answer."""


class IterationLimitExceeded(AgentLoopError):
    """The safety cap was reached before the model reported it had finished."""


class UnusableResponse(AgentLoopError):
    """The model returned a response the loop cannot act on."""


@dataclass(frozen=True)
class Event:
    """Something the loop did: a response (stop_reason set) or a tool call (result set)."""

    iteration: int
    stop_reason: str | None = None
    tool_name: str | None = None
    tool_input: Mapping[str, Any] | None = None
    result: ToolResult | None = None


def resolve_model(model: str | None = None) -> str:
    """The model asked for, else the environment's, else the default."""
    return model or os.environ.get(MODEL_VARIABLE) or DEFAULT_MODEL


def run(
    prompt: str,
    *,
    client: Any = None,
    model: str | None = None,
    max_iterations: int = MAX_ITERATIONS,
    on_event: Callable[[Event], None] | None = None,
) -> str:
    """Run the loop until the model reports it has finished, and return its answer.

    Raises `UnusableResponse` for a response the loop cannot act on, and
    `IterationLimitExceeded` if the safety cap is reached first. Neither is returned as
    an answer, so a caller cannot mistake a run that gave up for one that finished.
    """
    if client is None:
        import anthropic  # only when no client was supplied, so tests need no credential

        client = anthropic.Anthropic()
    model = resolve_model(model)
    emit = on_event or (lambda event: None)
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    for iteration in range(1, max_iterations + 1):
        response = client.messages.create(
            model=model, max_tokens=MAX_TOKENS, tools=TOOLS, messages=messages
        )
        stop_reason = response.stop_reason
        logger.info("iteration %d: stop_reason=%s", iteration, stop_reason)
        emit(Event(iteration=iteration, stop_reason=stop_reason))

        if stop_reason == FINISHED:
            return "\n".join(b.text for b in response.content if b.type == "text").strip()
        if stop_reason != REQUESTING_A_TOOL:
            logger.error("iteration %d: unusable stop reason %r", iteration, stop_reason)
            raise UnusableResponse(f"the model stopped with {stop_reason!r}")

        requests = [b for b in response.content if b.type == REQUESTING_A_TOOL]
        if not requests:
            # An empty turn is rejected outright; stopping here names the cause instead.
            logger.error("iteration %d: a tool was requested but none was named", iteration)
            raise UnusableResponse("the model reported a tool request but named no tool")

        # The response goes back whole. Rebuilding it from the parts the loop recognises
        # would drop any reasoning block, which must be returned unchanged.
        messages.append({"role": "assistant", "content": response.content})

        results = []
        for request in requests:
            result = dispatch(request.name, request.input)
            logger.info("iteration %d: %s -> %s", iteration, request.name, result.content)
            emit(Event(iteration, tool_name=request.name, tool_input=request.input, result=result))
            results.append({
                "type": "tool_result",
                "tool_use_id": request.id,
                "content": result.content,
                "is_error": result.is_error,
            })
        # Every result for this response goes back in one turn, never spread across several.
        messages.append({"role": "user", "content": results})

    logger.warning("reached the safety cap of %d iterations without finishing", max_iterations)
    raise IterationLimitExceeded(f"stopped after {max_iterations} iterations without finishing")
