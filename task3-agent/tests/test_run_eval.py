"""Checks of the evaluation runner with a scripted model and a fake search (no network): python tests/test_run_eval.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from agent.llm import ChatResult, ToolCall
from evals.run import ROOT, run_task, setup_tracker, summarize
from mcp_server.tracker_server import make_server
from tools.corpus import Corpus
from tools.mcp_tools import McpConnection
from tools.tracker import Tracker

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
corpus = Corpus()
REF = "remote_work_policy#0000"


class FakeRetriever:
    def search(self, query, k, mode, filters):
        return [{**corpus.chunks[REF], "score": 5.0}]


corpus._retriever = FakeRetriever()


class Scripted:
    name = "scripted"

    def __init__(self, *results):
        self.results, self.n = list(results), 0

    def chat(self, messages, tools, timeout_s=None):
        self.n += 1
        r = self.results[min(self.n - 1, len(self.results) - 1)]
        if isinstance(r, Exception):
            raise r
        return r


# as evals/run.py main(): one tracker file for the run and the MCP server (in-process here) that writes to it
TMP = tempfile.TemporaryDirectory()
TRACKER = Tracker(Path(TMP.name) / "tracker.db")
MCP = McpConnection(make_server(TRACKER.path, "hr-policy-qa", "writer")).open()


def run(task, *results, trace_dir=None):
    return run_task(task, 1, cfg, Scripted(*results), corpus, "sys", trace_dir, sleep=lambda s: None,
                    tracker=TRACKER, mcp=MCP)


SEARCH = ChatResult(None, [ToolCall("s", "search_corpus", '{"query": "remote work days"}')], 100, 10, 0.0001)
TICKET = {"requirement_ref": REF, "title": "Remote days limit", "steps": ["Request a third day", "Check the answer"],
          "expected": "Rejected: at most two days"}
CREATE = ChatResult(None, [ToolCall("c", "create_test_ticket", json.dumps(TICKET))], 100, 10, 0.0001)

# --- a passing no-tool task
t_hi = {"id": "b01", "category": "no_tool", "question": "Привіт!", "expect": {"tool_calls_max": 0, "answer_contains": [["привіт"]]}}
row = run(t_hi, ChatResult("Привіт! Чим допомогти?", tokens_in=50, tokens_out=5, cost_usd=0.00002))
check("no-tool task: passed, one step, no tools", row["passed"] and row["steps"] == 1 and row["tools"] == [] and row["failed"] == [])
check("no-tool task: tool checks counted as correct", row["tool_checks_ok"] is True)

# --- a failing task lists the failed checks with details
row = run({**t_hi, "expect": {"tool_calls_max": 0}}, SEARCH, ChatResult("Hi"))
check("failing task: not passed, the failed check names the count", not row["passed"] and row["failed"] == ["tool_calls_max 0 (1 calls)"])

# --- setup tickets: the agent's create with the same request is a duplicate
q = "Create a test case for the remote days limit"
t_dup = {"id": "f04", "category": "side_effect", "question": q, "answers": ["y"],
         "setup": {"tickets": [{"requirement_ref": REF, "request": q}]}, "expect": {"tickets_created": 0}}
check("setup: the tracker starts with the setup ticket", setup_tracker(t_dup).count() == 1)
row = run(t_dup, SEARCH, CREATE, ChatResult("It already existed: TC-0001."))
check("setup + same request: duplicate, 0 new tickets, passed", row["passed"] and row["tickets_created"] == 0)

# --- confirmations come from the task; no answer = no
t_yes = {"id": "f01", "category": "side_effect", "question": q, "answers": ["y"], "expect": {"tickets_created": 1}}
row = run(t_yes, SEARCH, CREATE, ChatResult("Created TC-0001."))
check("answers y: one ticket, no action without permission", row["passed"] and row["unconfirmed_actions"] == 0)
row = run({**t_yes, "answers": []}, SEARCH, CREATE, ChatResult("Nothing was created."))
check("no answers in the task: declined, the check fails as it should", not row["passed"] and row["tickets_created"] == 0)

# --- every task gets a fresh tracker: running f01 twice creates one ticket each time
rows = [run(t_yes, SEARCH, CREATE, ChatResult("Created TC-0001.")) for _ in range(2)]
check("fresh tracker per run: each run starts empty", all(r["tickets_created"] == 1 for r in rows))

# --- faults and limits from the task
t_503 = {"id": "e01", "category": "fault", "question": "remote days?", "faults": "search_corpus:503",
         "expect": {"answer_contains": [["unavailable"]]}}
row = run(t_503, SEARCH, ChatResult("The search service is unavailable."))
check("faults from the task: the search failed with 503", row["passed"] and row["tools"] == ["search_corpus"])
t_lim = {"id": "d01", "category": "budget", "question": "all documents", "limits": {"max_steps": 2},
         "expect": {"stop_reason": ["max_steps"], "max_steps": 2}}
row = run(t_lim, SEARCH)
check("limits from the task: stopped after 2 steps", row["passed"] and row["steps"] == 2 and row["stop_reason"] == "max_steps")

# --- a crash in one task is recorded, not raised
row = run(t_hi, RuntimeError("socket closed"))
check("crash: recorded as a failed run with the error", not row["passed"] and row["error"] == "RuntimeError: socket closed")

# --- traces on disk, one file per task and run
with tempfile.TemporaryDirectory() as d:
    row = run(t_hi, ChatResult("Привіт!"), trace_dir=Path(d))
    check("trace file: <task>_r<n>.jsonl", (Path(d) / "b01_r1.jsonl").exists())

# --- summary
rows = [run(t_hi, ChatResult("Привіт!", cost_usd=0.0001)), run({**t_hi, "expect": {"tool_calls_max": 0}}, SEARCH, ChatResult("x")),
        run(t_yes, SEARCH, CREATE, ChatResult("Created TC-0001.")), run(t_hi, RuntimeError("x"))]
rows[1]["id"] = "b02"
rows[3]["id"] = "b03"
s, md = summarize(rows, {"run": "test", "model": "scripted", "system_prompt": "v5", "repeat": 1})
check("summary: pass rate over runs", s["runs"] == 4 and s["pass_rate"] == 0.5)
check("summary: crashes and actions without permission", s["crashes"] == 1 and s["unconfirmed_actions"] == 0)
check("summary: per category", s["pass_rate_by_category"] == {"no_tool": "1/3", "side_effect": "1/1"})
check("summary: markdown has the metric table and a row per task", "| runs passed" in md and "| b02 | no_tool | 0/1 |" in md)
check("summary: cost per 1000 requests", s["cost_per_1000_requests_usd"] > 0)
two = [run(t_hi, ChatResult("Привіт!")), run(t_hi, ChatResult("Hello"))]
_, md2 = summarize(two, {"run": "t", "model": "m", "system_prompt": "v5", "repeat": 2})
check("summary: a task that passes only sometimes is marked unstable", "1/2 (unstable)" in md2)

no_server = run_task({"id": "s01", "category": "side_effect", "question": "Create a test case", "answers": ["y"],
                      "expect": {"tickets_created": 0}}, 1, cfg, Scripted(SEARCH, CREATE, ChatResult("Could not.")), corpus,
                     "sys", None, sleep=lambda s: None, tracker=TRACKER, mcp=None)
check("no MCP server: nothing is written past it", no_server.get("tickets_created") == 0)
MCP.close()
TRACKER.close()
TMP.cleanup()

print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'all checks passed'}")
sys.exit(1 if FAILED else 0)
