# Traceability: multi-tool agent loop

One row per requirement in
[`specs/multi-tool-agent-loop/spec.md`](./specs/multi-tool-agent-loop/spec.md). Requirement
identity is the requirement's name; this project has no numeric scheme.

Code paths are relative to `agent_loop/`. Tests live in `agent_loop/tests/`, run from the
repository root with `agent_loop/.venv/bin/python -m pytest agent_loop/tests`.

| Requirement | Code | Test |
|---|---|---|
| Offer a calculator tool | `tools.py:calculator`, `tools.py:TOOLS` | `test_each_tool_is_offered_with_a_description_and_its_input_schema[calculator]`, `test_an_arithmetic_expression_is_evaluated` |
| Offer a web search tool | `tools.py:web_search`, `tools.py:_STUB_RESULTS`, `tools.py:TOOLS` | `test_each_tool_is_offered_with_a_description_and_its_input_schema[web_search]`, `test_a_query_returns_a_stub_result_without_touching_the_network` |
| Let the model choose the tool | `loop.py:run` (sends `tools` but never `tool_choice`), the `description` fields in `tools.py:TOOLS` | `test_the_model_chooses_the_search_then_the_calculation_and_the_run_completes` (live) |
| Execute every requested tool and return its result | `loop.py:run` (the `for request in requests` block), `tools.py:dispatch`, `tools.py:_HANDLERS` | `test_a_result_is_returned_against_the_request_it_answers`, `test_a_tool_that_cannot_run_returns_an_error_to_the_model_and_the_loop_continues`, `test_a_requested_tool_runs_with_the_input_the_model_supplied`, `test_an_unknown_tool_or_unusable_input_reports_an_error_rather_than_raising` (4 cases) |
| Thread results back into the conversation | `loop.py:run` (appends `response.content` whole, then all results in one turn) | `test_the_models_response_is_added_to_the_conversation_whole`, `test_every_result_for_one_response_is_returned_in_a_single_turn` |
| Terminate only on the model's reported stop reason | `loop.py:FINISHED`, `loop.py:REQUESTING_A_TOOL`, the stop-reason branch in `loop.py:run` | `test_a_response_that_leads_with_text_but_requests_a_tool_continues_the_loop` (covers both the content-type and the wording shortcut), `test_the_loop_returns_the_text_when_the_model_reports_it_has_finished` |
| Support several tool calls in sequence | `loop.py:run` (the iteration loop and its accumulating `messages`) | `test_a_value_found_by_one_tool_is_carried_into_the_next_call_well_before_the_cap` |
| Cap the number of iterations for safety | `loop.py:MAX_ITERATIONS`, `loop.py:IterationLimitExceeded`, the `logger.warning` and `raise` after the loop | `test_a_value_found_by_one_tool_is_carried_into_the_next_call_well_before_the_cap` (a normal run ends under the cap, which is 20), `test_reaching_the_safety_cap_records_a_warning_and_cannot_be_received_as_an_answer` |
| Report a response the loop cannot act on | `loop.py:UnusableResponse` and its two raise sites in `loop.py:run` | `test_an_unrecognised_stop_reason_is_reported_rather_than_returned` (`max_tokens`, `refusal`), `test_a_tool_request_naming_no_tool_is_reported_and_no_empty_turn_is_sent` |
| Evaluate expressions without executing arbitrary code | `tools.py:_evaluate`, `tools.py:_BINARY`, `tools.py:_UNARY`, `tools.py:_Refused`, the guards in `tools.py:calculator` | `test_an_expression_that_is_not_arithmetic_is_refused` (4 cases), `test_a_refused_expression_is_never_evaluated`, `test_arithmetic_that_cannot_produce_a_real_value_is_refused_rather_than_raising` (5 cases: zero divisor, non-finite, malformed, complex, complex intermediate at `//`) |
| Refuse an expression whose result would be too large to compute | `tools.py:_refuse_unbounded_power`, `tools.py:MAX_RESULT_BITS`, the `ast.Pow` check in `tools.py:_evaluate` | `test_a_power_whose_result_would_be_enormous_is_refused_promptly` (2 cases incl. nesting), `test_ordinary_arithmetic_is_unaffected_by_the_bound` (4 cases incl. a float power) |
| Demonstrate the complete lifecycle against a live model | `tests/test_live.py`, `__main__.py` (the by-hand transcript), `tests/conftest.py:pytest_terminal_summary`, `tests/conftest.py:REQUIREMENTS_NEEDING_A_LIVE_MODEL` | `test_the_model_chooses_the_search_then_the_calculation_and_the_run_completes` (live), `test_the_run_names_the_unverified_requirements_when_there_is_no_credential`, `test_nothing_is_reported_as_unverified_when_a_credential_is_present`, `test_the_run_does_not_claim_the_rest_was_verified_when_tests_failed`, and the transcript the entry point prints (`tests/test_cli.py`, 2 tests) |

## Notes

**The security-sensitive requirement is asserted directly.** *Evaluate expressions without
executing arbitrary code* is covered by tests that submit input designed to execute code -
`__import__`, an attribute reach, a comprehension, a string operation - and assert refusal.
`test_a_refused_expression_is_never_evaluated` additionally proves the refusal happens *before*
evaluation, by asserting that a file the expression would have written does not exist.

**One test was proved able to fail, twice.** The stop-reason branch was replaced with the
content-type check the change request forbids (`response.content[0].type == "text"`). Before the
suite was trimmed, eight tests went red; after, four - in both cases including the test protecting
*Terminate only on the model's reported stop reason*. The branch was restored each time and the
suite returned to green.

**Two requirements need a live model** and are listed in
`tests/conftest.py:REQUIREMENTS_NEEDING_A_LIVE_MODEL`. When `ANTHROPIC_API_KEY` is absent the
suite still passes, and names them as unverified in its summary rather than omitting them
silently.

**Review pass one raised three code findings, all fixed.** A negative base raised to a fractional
power returned a complex number as a successful result, bypassing the finite check - the spec's
refusal scenario was widened to name a non-real result, and the tool now refuses it. The
unverified-requirements summary claimed "everything else was verified" even when tests had
failed; it now reports failures instead. The entry point asserted that an event without a stop
reason carried a tool result, so a `None` stop reason produced a traceback; it now branches on
the result.

**Review pass two raised one further finding, fixed, and a closing pass confirmed it:
`Ready to merge: yes`.** A complex intermediate reaching `//` or `%` raised `TypeError` out of
the tool instead of returning an error result. `TypeError` now returns the refusal, and the
closing pass verified ordinary `//` and `%` unchanged across 338 differential cases.

**The suite was then trimmed on request, from 68 tests to 42 and from 1,098 lines of code and
tests to 721.** Every scenario in the spec still maps to a test - the reduction merged tests
that asserted the same scenario from two angles, and cut parametrised cases that exercised the
same branch. No requirement lost coverage; the mapping above is the post-trim state.

## Results

- 42 tests pass with a credential present.
- 41 pass and 1 is skipped without one, with the skipped requirement named in the run's summary.
- `sdd_django_demo` is untouched: its suite still reports 131 passing.
