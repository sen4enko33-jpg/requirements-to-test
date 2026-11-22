"""Fault injection: replace the answers of tools with failures, to check how the agent behaves when a service breaks.

    FAULTS=503 python main.py "..."                       every tool answers 503
    FAULTS=search_corpus:timeout python main.py "..."     only search_corpus times out
    FAULTS=search_corpus:503*1 python main.py "..."       the first call fails, the next ones work (a retry recovers)
    FAULTS=schema,list_documents:429 python main.py "..."

An item is [tool:]kind[*n]: without a tool it applies to every tool, without *n to every call. Kinds:
  timeout   the client of the service times out (raised at once instead of waiting, so the checks are fast)
  429       rate limited, with Retry-After: 1 s
  503       service unavailable
  schema    the service changed its format: the first field of every item of the answer list is renamed
            (for example results[].ref -> results[].ref_v2), so the output schema of the tool rejects it
The counters count the attempts of the tool, retries included: with 503*1 the first attempt fails and the retry works.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .registry import Tool, ToolRegistry, ToolUnavailable

KINDS = ("timeout", "429", "503", "schema")
ITEM = re.compile(r"^(?:(?P<tool>[a-z_]+):)?(?P<kind>timeout|429|503|schema)(?:\*(?P<n>\d+))?$")


@dataclass
class Fault:
    kind: str
    tool: str | None = None     # None = every tool
    times: int | None = None    # None = every call; n = only the first n attempts
    used: int = 0

    def active(self, tool: str) -> bool:
        return (self.tool is None or self.tool == tool) and (self.times is None or self.used < self.times)


def parse(spec: str | None) -> list[Fault]:
    faults = []
    for item in (spec or "").replace(" ", "").split(","):
        if not item:
            continue
        m = ITEM.match(item)
        if not m:
            raise ValueError(f"bad FAULTS item {item!r}: expected [tool:]kind[*n] with kind in {KINDS}")
        faults.append(Fault(m["kind"], m["tool"], int(m["n"]) if m["n"] else None))
    return faults


def _rename_first_fields(result):
    """The answer of a changed API: in the first list of the answer, the first field of every item gets another name."""
    if not isinstance(result, dict):
        return result
    out = dict(result)
    for key, value in result.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            out[key] = [{(f"{k}_v2" if i == 0 else k): v for i, (k, v) in enumerate(item.items())} for item in value]
            break
    return out


def wrap(tool: Tool, faults: list[Fault]) -> Tool:
    mine = [f for f in faults if f.tool is None or f.tool == tool.name]
    if not mine:
        return tool
    inner = tool.fn

    def fn(args):
        for f in mine:
            if f.active(tool.name):
                f.used += 1
                if f.kind == "timeout":
                    raise ToolUnavailable(None, f"[fault] {tool.name}: timed out")
                if f.kind == "429":
                    raise ToolUnavailable(429, "[fault] HTTP 429 Too Many Requests", retry_after_s=1.0)
                if f.kind == "503":
                    raise ToolUnavailable(503, "[fault] HTTP 503 Service Unavailable")
                if f.kind == "schema":
                    return _rename_first_fields(inner(args))
        return inner(args)

    return Tool(tool.name, tool.description, tool.args_model, fn, tool.safe, tool.side_effect, tool.version, tool.output_model)


def apply(registry: ToolRegistry, spec: str | None) -> list[Fault]:
    """Wrap the tools of the registry in place; unknown tool names in the spec are an error (a typo would test nothing)."""
    faults = parse(spec)
    unknown = {f.tool for f in faults if f.tool and f.tool not in registry.tools}
    if unknown:
        raise ValueError(f"FAULTS names unknown tool(s) {sorted(unknown)}; tools: {sorted(registry.tools)}")
    for name, tool in list(registry.tools.items()):
        registry.tools[name] = wrap(tool, faults)
    return faults
