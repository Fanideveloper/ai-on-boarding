"""A stub model client, response builders, and the unverified-requirement report."""

from __future__ import annotations

import os
from types import SimpleNamespace as NS
from typing import Any

CREDENTIAL = "ANTHROPIC_API_KEY"
REQUIREMENTS_NEEDING_A_LIVE_MODEL = [
    "Let the model choose the tool",
    "Demonstrate the complete lifecycle against a live model",
]


def has_credential() -> bool:
    return bool(os.environ.get(CREDENTIAL))


def text(t: str) -> NS:
    return NS(type="text", text=t)


def thinking(signature: str = "sig") -> NS:
    return NS(type="thinking", thinking="", signature=signature)


def tool_use(name: str, tool_input: dict[str, Any], id: str = "req-1") -> NS:
    return NS(type="tool_use", id=id, name=name, input=tool_input)


def response(stop_reason: str, *content: Any) -> NS:
    return NS(stop_reason=stop_reason, content=list(content))


def requesting(*blocks: Any) -> NS:
    return response("tool_use", *blocks)


def finished(t: str = "done") -> NS:
    return response("end_turn", text(t))


class StubClient:
    """Returns scripted responses and records every request it was sent."""

    def __init__(self, *responses: Any) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    @property
    def messages(self) -> "StubClient":
        return self

    def create(self, **kwargs: Any) -> Any:
        # The loop appends to the same list, so snapshot it to see what was sent now.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        assert self._responses, "the loop made more requests than the stub was given"
        return self._responses.pop(0)

    @property
    def conversation(self) -> list[dict[str, Any]]:
        return self.requests[-1]["messages"]


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:  # noqa: ARG001
    """Name what went unverified, rather than passing over it.

    A suite that reports success having quietly stopped checking something is read as
    evidence that it checked.
    """
    if has_credential():
        return
    terminalreporter.write_sep("=", "unverified requirements", yellow=True, bold=True)
    terminalreporter.write_line(f"{CREDENTIAL} is not set, so the live lifecycle check did not run.")
    for requirement in REQUIREMENTS_NEEDING_A_LIVE_MODEL:
        terminalreporter.write_line(f"  UNVERIFIED  Requirement: {requirement}")
    if exitstatus == 0:
        terminalreporter.write_line("Everything else was verified. Set the credential to verify these.")
    else:
        terminalreporter.write_line("Other requirements were NOT all verified either - see failures above.")
