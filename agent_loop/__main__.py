"""Run the agent loop by hand and watch it work.

    python -m agent_loop "What is the population of Tokyo divided by 1000?"

Prints the stop reason that drove each iteration and every tool call with its result,
so the lifecycle is visible rather than inferred from the final answer.
"""

from __future__ import annotations

import argparse
import sys

from agent_loop.loop import AgentLoopError, Event, resolve_model, run

DEFAULT_PROMPT = "What is the population of Tokyo divided by 1000?"


def _show(event: Event) -> None:
    if event.result is None:  # a response event - including one whose stop reason is absent
        print(f"iter {event.iteration}  stop_reason={event.stop_reason}")
        return
    mark = "!" if event.result.is_error else " "
    arguments = ", ".join(f"{k}={v!r}" for k, v in (event.tool_input or {}).items())
    print(f"       ->{mark} {event.tool_name}({arguments})\n       <-{mark} {event.result.content}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent_loop", description=__doc__)
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT)
    parser.add_argument("--model", default=None, help="override the model for this run")
    args = parser.parse_args(argv)

    print(f"model: {resolve_model(args.model)}\ntask:  {args.prompt}\n")
    try:
        answer = run(args.prompt, model=args.model, on_event=_show)
    except AgentLoopError as exc:
        print(f"\nno answer: {exc}", file=sys.stderr)
        return 1
    print(f"\nanswer: {answer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
