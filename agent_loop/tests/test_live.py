"""The live-model check, and the report that runs when it cannot be performed.

*Let the model choose the tool* is a claim about the model's judgement, not about this
code, so it needs a live model. When no credential is present the check does not run,
and the run says so.
"""

from __future__ import annotations

import pytest

from agent_loop.loop import Event, run
from agent_loop.tests.conftest import (
    CREDENTIAL, REQUIREMENTS_NEEDING_A_LIVE_MODEL, has_credential, pytest_terminal_summary,
)


# --- Requirements: Let the model choose the tool / Demonstrate the complete lifecycle ---------


@pytest.mark.skipif(not has_credential(), reason=f"needs {CREDENTIAL} - reported in the summary")
def test_the_model_chooses_the_search_then_the_calculation_and_the_run_completes():
    """Asserts the tools the model chose and that the run finished - not the answer's wording."""
    chosen: list[str] = []
    answer = run(
        "What is the population of Tokyo divided by 1000?",
        on_event=lambda e: chosen.append(e.tool_name) if e.tool_name else None,
    )
    assert chosen == ["web_search", "calculator"], f"the model chose {chosen}"
    assert "14180" in answer.replace(",", "")


# --- Requirement: Demonstrate the complete lifecycle (the unverified-report half) --------------


class _FakeReporter:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write_sep(self, sep, title, **kw) -> None:
        self.lines.append(title)

    def write_line(self, line, **kw) -> None:
        self.lines.append(line)


def _summary(monkeypatch, credential: str | None, exitstatus: int) -> str:
    if credential is None:
        monkeypatch.delenv(CREDENTIAL, raising=False)
    else:
        monkeypatch.setenv(CREDENTIAL, credential)
    reporter = _FakeReporter()
    pytest_terminal_summary(reporter, exitstatus=exitstatus, config=None)
    return "\n".join(reporter.lines)


def test_the_run_names_the_unverified_requirements_when_there_is_no_credential(monkeypatch):
    reported = _summary(monkeypatch, credential=None, exitstatus=0)
    assert "UNVERIFIED" in reported
    assert all(r in reported for r in REQUIREMENTS_NEEDING_A_LIVE_MODEL)


def test_nothing_is_reported_as_unverified_when_a_credential_is_present(monkeypatch):
    assert _summary(monkeypatch, credential="sk-ant-not-real", exitstatus=0) == ""


def test_the_run_does_not_claim_the_rest_was_verified_when_tests_failed(monkeypatch):
    reported = _summary(monkeypatch, credential=None, exitstatus=1)
    assert "Everything else was verified" not in reported
    assert "NOT all verified" in reported
