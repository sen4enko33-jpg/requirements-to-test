"""The tool set of one agent request, shared by main.py and the evaluation runner."""
from __future__ import annotations

import sys

from . import faults
from .corpus import Corpus
from .corpus_tools import make_corpus_tools
from .registry import RetryPolicy, ToolRegistry
from .session import Session
from .ticket_tool import make_ticket_tool
from .tracker import Tracker


def build_registry(cfg: dict, corpus: Corpus, tracker: Tracker, session: Session, fault_spec: str | None = None,
                   sleep=None, quiet: bool = False) -> ToolRegistry:
    """The four tools for one request. corpus: loaded once and shared (warm_up() it first); tracker, session: per request;
    fault_spec: FAULTS (tools/faults.py), counted per request; sleep: replaces the backoff pauses in tests."""
    tools = make_corpus_tools(corpus, session=session) + [make_ticket_tool(tracker, corpus, session)]
    kw = {"sleep": sleep} if sleep is not None else {}
    registry = ToolRegistry(tools, RetryPolicy.from_config(cfg.get("tool_retry")), **kw)
    if fault_spec:
        faults.apply(registry, fault_spec)
        if not quiet:
            print(f"[faults: {fault_spec}]", file=sys.stderr)
    return registry
