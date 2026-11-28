"""The agent of task 3 in one command:  python main.py "your question"

  python main.py "Hello, what can you do?"
  python main.py "How many days a week can employees work remotely?"
  python main.py "Which documents are about weather?" --max-steps 3

The search over the corpus uses the Chroma index of task 2: build it once in ../task2-rag with python -m rag.retrieval.build.

Test cases: "Create a test case for <requirement>" files one in data/tms.db after you confirm it in the terminal (y/N).
Without a terminal the change is declined; --answers y,n gives the answers in advance (logged as by=script in the trace).

Fault injection (tools/faults.py): FAULTS=search_corpus:503 python main.py "..." (also timeout, 429, schema, *n).

The test cases already in the TMS are read through the MCP server mcp_server/tms_server.py: main.py starts it as a
subprocess for the request (config.yaml, section mcp) and its tools list_test_cases / get_test_case join the agent's tools.
New test cases are written by the same server (create_test_case, after your confirmation). Its log goes to
traces/mcp_tms.log. If it does not start, the agent runs without these tools and cannot create test cases.

Needs OPENROUTER_API_KEY in .env (repository root or this folder). Every run writes its trace to traces/<run_id>.jsonl."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent.confirm import CliConfirmer, ScriptedConfirmer  # noqa: E402
from agent.limits import Limits  # noqa: E402
from agent.llm import make_model  # noqa: E402
from agent.loop import run_agent  # noqa: E402
from agent.trace import Trace  # noqa: E402
from tools.build import build_registry  # noqa: E402
from tools.corpus import Corpus  # noqa: E402
from tools.mcp_tools import McpTmsStore, mcp_tools, open_server  # noqa: E402
from tools.session import Session  # noqa: E402
from tools.tms import Tms  # noqa: E402


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def load_system_prompt(version: str) -> str:
    return (ROOT / "prompts" / f"system_{version}.md").read_text(encoding="utf-8").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", help="the question to the agent")
    ap.add_argument("--max-steps", type=int, help="override limits.max_steps of config.yaml")
    ap.add_argument("--max-cost", type=float, help="override limits.max_cost_usd of config.yaml")
    ap.add_argument("--answers", help="confirmations given in advance, in order, e.g. y or y,n (default: ask in the terminal)")
    a = ap.parse_args()

    load_dotenv(ROOT / ".env"); load_dotenv(ROOT.parent / ".env")
    cfg = load_config()
    key = (os.getenv(cfg["model"]["api_key_env"]) or "").strip()   # a pasted key often ends with a newline: invalid in a header
    if key in {"your-key-here", ""}:
        sys.exit(f"no {cfg['model']['api_key_env']}: copy .env.example to .env (repository root) and put the key there")
    limits = Limits.from_config(cfg["limits"])
    if a.max_steps is not None:
        limits.max_steps = a.max_steps
    if a.max_cost is not None:
        limits.max_cost_usd = a.max_cost

    if a.answers is not None:
        confirm = ScriptedConfirmer(*[x.strip().lower() in CliConfirmer.YES for x in a.answers.split(",") if x.strip()])
    else:
        confirm = CliConfirmer()
    trace = Trace(ROOT / cfg["trace_dir"])
    session = Session(run_id=trace.run_id, request=a.question)
    corpus = Corpus()
    corpus.warm_up()          # load the search models now, not inside the first tool call (its timeout is short)
    tms = Tms()
    conn = open_server(cfg, "tms", db=tms.path)       # the server reads the same file the agent writes
    try:
        tools = build_registry(cfg, corpus, tms, session, os.getenv("FAULTS"),
                               extra_tools=mcp_tools(conn, cfg["mcp"]["tms"].get("hidden", ())) if conn else [],
                               ticket_store=McpTmsStore(conn))        # test cases are written by the server
        result = run_agent(a.question, make_model(cfg, key), tools, limits,
                           load_system_prompt(cfg["system_prompt"]), trace, confirm=confirm)
    finally:
        if conn:
            conn.close()
    print(result.answer)
    u = result.usage
    print(f"\n[stop: {result.stop_reason} | steps {u['steps']} | tokens {u['tokens_in']}+{u['tokens_out']} | "
          f"${u['cost_usd']:.5f} | {u['elapsed_s']:.1f} s | tools: {[c['name'] for c in result.tool_calls] or '-'}]")
    print(f"[trace: {result.trace_path}]")
    return 0 if result.complete else 2


if __name__ == "__main__":
    sys.exit(main())
