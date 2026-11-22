"""Checks of create_test_ticket: required arguments, only refs the agent has read, idempotency through the tool
(no network, no models): python tests/test_ticket_tool.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.confirm import ScriptedConfirmer
from agent.limits import Limits
from agent.llm import ChatResult, ToolCall
from agent.loop import run_agent
from agent.trace import Trace
from tools.corpus import Corpus
from tools.corpus_tools import make_corpus_tools
from tools.registry import ToolRegistry
from tools.session import Session
from tools.ticket_tool import make_ticket_tool
from tools.tracker import Tracker

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


corpus = Corpus()
pol = [c for c in corpus.chunks if c.startswith("remote_work_policy#")]


class FakeRetriever:
    def search(self, query, k, mode, filters):
        return [{**corpus.chunks[pol[0]], "score": 5.0}]


corpus._retriever = FakeRetriever()


def setup():
    session, tracker = Session(run_id="run-x"), Tracker(":memory:")
    reg = ToolRegistry(make_corpus_tools(corpus, floor=None, session=session) + [make_ticket_tool(tracker, corpus, session)],
                       sleep=lambda s: None)
    return reg, session, tracker


GOOD = {"requirement_ref": pol[0], "title": "Remote days limit after probation",
        "steps": ["Log in as an employee after probation", "Request a third remote day in one week"],
        "expected": "The request is rejected: at most two remote days per week."}


def call(reg, name, args):
    return reg.execute(name, json.dumps(args), 5)


# --- the tool itself
reg, session, tracker = setup()
t = reg.tools["create_test_ticket"]
check("marked as a side effect and not safe to repeat", t.side_effect and not t.safe and t.version == "v1")
params = t.schema()["function"]["parameters"]
check("all four arguments are required", sorted(params["required"]) == ["expected", "requirement_ref", "steps", "title"])

# --- a ref that was not read in this conversation
out = call(reg, "create_test_ticket", GOOD)
check("ref not seen in this conversation -> invalid_args, nothing written",
      out.error_kind == "invalid_args" and "search for the requirement first" in out.content and tracker.count() == 0)
out = call(reg, "create_test_ticket", {**GOOD, "requirement_ref": "remote_work_policy#0999"})
check("ref that does not exist -> invalid_args", out.error_kind == "invalid_args" and "unknown requirement_ref" in out.content)

# --- after a search the ref is accepted
call(reg, "search_corpus", {"query": "remote work days"})
check("search records the returned refs in the session", pol[0] in session.seen_refs)
out = call(reg, "create_test_ticket", GOOD)
data = json.loads(out.content)
check("create: ok, TC-0001, created, doc_id taken from the passage",
      out.ok and data == {"ticket": "TC-0001", "created": True, "duplicate": False, "doc_id": "remote_work_policy",
                          "requirement_ref": pol[0], "title": GOOD["title"]})
check("create: stored with the run id of the request", tracker.all()[0]["run_id"] == "run-x" and tracker.count() == 1)

# --- idempotency through the tool
out = call(reg, "create_test_ticket", {**GOOD, "title": GOOD["title"].upper(), "steps": ["other"] * 2})
data = json.loads(out.content)
check("the same test case again: duplicate, the existing ticket, nothing new written",
      out.ok and data["duplicate"] and data["ticket"] == "TC-0001" and tracker.count() == 1)
check("never retried: one attempt", out.attempts == 1)

# --- get_passage also counts as reading
reg2, session2, tracker2 = setup()
call(reg2, "get_passage", {"ref": pol[1], "before": 1})
check("get_passage records the passage and its neighbours", {pol[0], pol[1]} <= session2.seen_refs)

# --- missing or bad arguments: rejected, nothing written
reg, session, tracker = setup()
session.saw([pol[0]])
for missing in ("requirement_ref", "title", "steps", "expected"):
    args = {k: v for k, v in GOOD.items() if k != missing}
    out = call(reg, "create_test_ticket", args)
    check(f"missing {missing}: invalid_args naming it", out.error_kind == "invalid_args" and missing in out.content)
for bad, why in [({"steps": []}, "no steps"), ({"steps": ["ok step", "x"]}, "a step of 1 char"), ({"title": "TC"}, "title too short"),
                 ({"steps": ["step"] * 11}, "11 steps"), ({"requirement_ref": "remote_work_policy"}, "ref without #nnnn")]:
    out = call(reg, "create_test_ticket", {**GOOD, **bad})
    check(f"{why}: invalid_args", out.error_kind == "invalid_args")
check("nothing was written by the rejected calls", tracker.count() == 0)

# --- in the loop with a scripted model: search -> create
reg, session, tracker = setup()


class Scripted:
    name = "scripted"

    def __init__(self, *results):
        self.results, self.n = list(results), 0

    def chat(self, messages, tools, timeout_s=None):
        self.n += 1
        return self.results[min(self.n - 1, len(self.results) - 1)]


m = Scripted(ChatResult(None, [ToolCall("c0", "search_corpus", '{"query": "remote work days per week"}')]),
             ChatResult(None, [ToolCall("c1", "create_test_ticket", json.dumps(GOOD))]),
             ChatResult("Created test case TC-0001."))
r = run_agent("Create a test case for the remote days limit", m, reg, Limits(), "sys", Trace(), confirm=ScriptedConfirmer(True))
check("loop: search then create -> one ticket", r.stop_reason == "answered" and tracker.count() == 1
      and [c["name"] for c in r.tool_calls] == ["search_corpus", "create_test_ticket"])

reg, session, tracker = setup()
m = Scripted(ChatResult(None, [ToolCall("c0", "create_test_ticket", json.dumps(GOOD))]),
             ChatResult("I need to know which requirement you mean."))
asker = ScriptedConfirmer(True)
r = run_agent("Create a test case", m, reg, Limits(), "sys", Trace(), confirm=asker)
check("loop: create without a search first -> rejected, no ticket", tracker.count() == 0 and r.tool_calls[0]["error_kind"] == "invalid_args")
check("loop: the person is not asked about an invented requirement", asker.asked == [])

print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'all checks passed'}")
sys.exit(1 if FAILED else 0)
