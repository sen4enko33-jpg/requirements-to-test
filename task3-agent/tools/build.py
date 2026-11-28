"""The tool set of one agent request, shared by main.py and the evaluation runner."""
from __future__ import annotations

import sys

from . import faults
from .corpus import Corpus
from .corpus_tools import make_corpus_tools
from .registry import RetryPolicy, Tool, ToolRegistry
from .session import Session
from .ticket_tool import make_ticket_tool
from .tms import Tms


def build_registry(cfg: dict, corpus: Corpus, tms: Tms, session: Session, fault_spec: str | None = None,
                   sleep=None, quiet: bool = False, extra_tools: list[Tool] | None = None,
                   ticket_store=None) -> ToolRegistry:
    """The tools for one request. corpus: loaded once and shared (warm_up() it first); tms, session: per request;
    fault_spec: FAULTS (tools/faults.py), counted per request, applied to the extra tools too; sleep: replaces the backoff
    pauses in tests; extra_tools: the tools of the MCP servers (tools/mcp_tools.py); ticket_store: where create_test_ticket
    writes (McpTmsStore: the MCP server), default the tms itself."""
    store = ticket_store if ticket_store is not None else tms
    tools = make_corpus_tools(corpus, session=session) + [make_ticket_tool(store, corpus, session)] + list(extra_tools or [])
    kw = {"sleep": sleep} if sleep is not None else {}
    registry = ToolRegistry(tools, RetryPolicy.from_config(cfg.get("tool_retry")), **kw)
    if fault_spec:
        faults.apply(registry, fault_spec)
        if not quiet:
            print(f"[faults: {fault_spec}]", file=sys.stderr)
    return registry
