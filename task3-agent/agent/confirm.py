"""Human confirmation of tool calls that change something outside the conversation (Tool.side_effect).

The agent loop calls the confirmer in code before such a tool runs; the model cannot skip it, whatever the prompt or a
document says. Without a "yes" the tool does not run and the model gets ERROR: not_confirmed. The default is to decline:
an agent run without a person (tests, evaluation, a pipe) never changes data unless the run says so explicitly."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass
class Decision:
    approved: bool
    by: str                 # who decided: user | default | script
    note: str = ""


class Confirmer(Protocol):
    def __call__(self, tool: str, args: dict) -> Decision: ...


def deny_all(tool: str, args: dict) -> Decision:
    return Decision(False, "default", "no person to ask: side effects are declined by default")


class ScriptedConfirmer:
    """For tests and evaluations: answers in order (True / False), then `then` for every further question; records the
    questions it was asked."""

    def __init__(self, *answers: bool, then: bool = False):
        self.answers, self.then, self.asked = list(answers), then, []

    def __call__(self, tool: str, args: dict) -> Decision:
        self.asked.append({"tool": tool, "args": args})
        ok = self.answers.pop(0) if self.answers else self.then
        return Decision(ok, "script")


def preview(tool: str, args: dict) -> str:
    """What the person sees before saying yes: the tool and every argument as it will be executed."""
    lines = [f"The agent wants to run {tool} (it changes data):"]
    for k, v in args.items():
        if isinstance(v, list):
            lines.append(f"  {k}:")
            lines += [f"    {i}. {x}" for i, x in enumerate(v, 1)]
        else:
            lines.append(f"  {k}: {v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}")
    return "\n".join(lines)


class CliConfirmer:
    """Asks in the terminal. Only an explicit y/yes/т/так approves; Enter, anything else, or no terminal declines."""

    YES = {"y", "yes", "т", "так"}

    def __init__(self, ask: Callable[[str], str] = input, out=sys.stderr, interactive: bool | None = None):
        self.ask, self.out = ask, out
        self.interactive = sys.stdin.isatty() if interactive is None else interactive

    def __call__(self, tool: str, args: dict) -> Decision:
        if not self.interactive:
            return Decision(False, "default", "not an interactive terminal: declined")
        print("\n" + preview(tool, args), file=self.out)
        try:
            answer = self.ask("Allow? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        return Decision(answer in self.YES, "user", answer or "(empty)")
