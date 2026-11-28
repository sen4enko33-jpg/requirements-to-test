"""Checks of the human confirmation of side effects and of a lost answer after a write (no network, no models):
python tests/test_confirm.py"""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.confirm import CliConfirmer, ScriptedConfirmer, preview
from agent.limits import Limits
from agent.llm import ChatResult, ToolCall
from agent.loop import run_agent
from agent.trace import Trace
from tools import faults
from tools.corpus import Corpus
from tools.corpus_tools import make_corpus_tools
from tools.registry import ToolRegistry
from tools.session import Session
from tools.ticket_tool import make_ticket_tool
from tools.tms import Tms

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


corpus = Corpus()
pol = [c for c in corpus.chunks if c.startswith("remote_work_policy#")]


class FakeRetriever:
    def search(self, query, k, mode, filters):
        return [{**corpus.chunks[pol[0]], "score": 5.0}, {**corpus.chunks[pol[2]], "score": 4.0}]


corpus._retriever = FakeRetriever()
GOOD = {"requirement_ref": pol[0], "title": "Remote days limit after probation",
        "steps": ["Log in as an employee after probation", "Request a third remote day in one week"],
        "expected": "The request is rejected: at most two remote days per week."}
SEARCH = ToolCall("s0", "search_corpus", '{"query": "remote work days"}')


REQUEST = "Create a test case for the remote days limit"


def setup(tms=None, fault=None, request=REQUEST):
    session, tms = Session(request=request), tms or Tms(":memory:")
    reg = ToolRegistry(make_corpus_tools(corpus, floor=None, session=session) + [make_ticket_tool(tms, corpus, session)],
                       sleep=lambda s: None)
    if fault:
        faults.apply(reg, fault)
    return reg, tms


class Scripted:
    name = "scripted"

    def __init__(self, *results):
        self.results, self.seen = list(results), []

    def chat(self, messages, tools, timeout_s=None):
        self.seen.append(messages)
        return self.results[min(len(self.seen) - 1, len(self.results) - 1)]


def create(i, args=GOOD):
    return ToolCall(f"c{i}", "create_test_ticket", json.dumps(args))


def run(model, reg, confirm=None):
    trace = Trace()
    r = run_agent("Create a test case for the remote days limit", model, reg, Limits(), "sys", trace, confirm=confirm)
    return r, trace


def last_tool_result(m):
    return [x for x in m.seen[-1] if x["role"] == "tool"][-1]["content"]


# --- default: nobody to ask -> declined, nothing written
reg, tms = setup()
m = Scripted(ChatResult(None, [SEARCH]), ChatResult(None, [create(1)]), ChatResult("Nothing was created."))
r, trace = run(m, reg)
check("default (no confirmer): declined, no ticket", tms.count() == 0 and r.tool_calls[1]["error_kind"] == "not_confirmed")
check("default: the model is told it was not allowed", last_tool_result(m).startswith("ERROR: not_confirmed:"))
ev = trace.of("confirm")[0]
check("default: the decision is in the trace", ev["approved"] is False and ev["by"] == "default" and ev["name"] == "create_test_ticket")

# --- approved: written; the person saw exactly the executed arguments
reg, tms = setup()
asker = ScriptedConfirmer(True)
m = Scripted(ChatResult(None, [SEARCH]), ChatResult(None, [create(1)]), ChatResult("Created TC-0001."))
r, trace = run(m, reg, asker)
check("approved: one ticket", tms.count() == 1 and r.tool_calls[1]["ok"] and r.tool_calls[1]["confirmed"] is True)
check("approved: the person was asked once, with the exact arguments", asker.asked == [{"tool": "create_test_ticket", "args": GOOD}])
check("approved: trace has confirm before the tool event",
      [e["event"] for e in trace.events if e["event"] in ("confirm", "tool")] == ["tool", "confirm", "tool"])
check("read-only tools never ask", r.tool_calls[0]["confirmed"] is None)

# --- declined, then the model tries again (other title): not asked again, nothing written
reg, tms = setup()
asker = ScriptedConfirmer(False, then=True)
other = {**GOOD, "title": "Another try with another title"}
m = Scripted(ChatResult(None, [SEARCH]), ChatResult(None, [create(1)]), ChatResult(None, [create(2, other)]),
             ChatResult("Nothing was created."))
r, trace = run(m, reg, asker)
check("declined + retry: still no ticket", tms.count() == 0)
check("declined + retry: the person is asked only once", len(asker.asked) == 1)
check("declined + retry: the second call gets 'already declined'",
      "already declined" in last_tool_result(m) and r.tool_calls[2]["error_kind"] == "not_confirmed")
check("declined + retry: trace marks the second refusal as a rule", trace.of("confirm")[1]["by"] == "rule")

# --- invalid calls are rejected before anyone is asked
reg, tms = setup()
asker = ScriptedConfirmer(True)
bad = {k: v for k, v in GOOD.items() if k != "expected"}
m = Scripted(ChatResult(None, [SEARCH]), ChatResult(None, [create(1, bad)]), ChatResult("Which result is expected?"))
r, _ = run(m, reg, asker)
check("missing argument: invalid_args, the person is not asked", asker.asked == [] and r.tool_calls[1]["error_kind"] == "invalid_args")
m = Scripted(ChatResult(None, [create(1, {**GOOD, "requirement_ref": pol[1]})]), ChatResult("Which requirement?"))
r, _ = run(m, reg, asker)
check("ref not read in this request: invalid_args, the person is not asked", asker.asked == [] and tms.count() == 0)

# --- two creates in one step: each is confirmed on its own
reg, tms = setup()
asker = ScriptedConfirmer(True, False)
m = Scripted(ChatResult(None, [SEARCH]), ChatResult(None, [create(1), create(2, {**GOOD, "requirement_ref": pol[2], "title": "VPN rule"})]),
             ChatResult("One created."))
r, _ = run(m, reg, asker)
check("two creates: yes for the first, no for the second -> one ticket",
      tms.count() == 1 and [c["confirmed"] for c in r.tool_calls[1:]] == [True, False])

# --- lost answer: the write happened, the agent saw a timeout; the repeated request does not duplicate
tr = Tms(":memory:")
reg, _ = setup(tr, fault="create_test_ticket:lost")
m = Scripted(ChatResult(None, [SEARCH]), ChatResult(None, [create(1)]), ChatResult("The service did not answer."))
r, _ = run(m, reg, ScriptedConfirmer(True))
check("lost: the ticket exists although the agent got an error", tr.count() == 1 and r.tool_calls[1]["error_kind"] == "timeout")
check("lost: the write is not retried by the registry (one attempt)", r.tool_calls[1]["attempts"] == 1)
reg2, _ = setup(tr)                                  # the user repeats the request: a new session, the same TMS
m2 = Scripted(ChatResult(None, [SEARCH]), ChatResult(None, [create(1)]), ChatResult("It already existed: TC-0001."))
r2, _ = run(m2, reg2, ScriptedConfirmer(True))
res = json.loads(last_tool_result(m2))
check("lost + repeated request: duplicate=true, still one ticket", tr.count() == 1 and res["duplicate"] and res["ticket"] == "TC-0001")
# --- the real-run bug of 1.4.4: the model writes another title on the repeated request
tr = Tms(":memory:")
for title in ("Test Maximum Remote Work Days", "Maximum Remote Work Days Test Case"):
    reg, _ = setup(tr)
    m = Scripted(ChatResult(None, [SEARCH]), ChatResult(None, [create(1, {**GOOD, "title": title})]), ChatResult("done"))
    run(m, reg, ScriptedConfirmer(True))
check("same request, another title written by the model: still one ticket", tr.count() == 1)
reg, _ = setup(tr, request="  create a TEST case for the remote   days limit ")
m = Scripted(ChatResult(None, [SEARCH]), ChatResult(None, [create(1, {**GOOD, "title": "Third title"})]), ChatResult("done"))
run(m, reg, ScriptedConfirmer(True))
check("same request with other case/spaces: still one ticket", tr.count() == 1)
reg, _ = setup(tr, request="Create a NEGATIVE test case for the remote days limit")
m = Scripted(ChatResult(None, [SEARCH]), ChatResult(None, [create(1, {**GOOD, "title": "Negative case"})]), ChatResult("done"))
run(m, reg, ScriptedConfirmer(True))
check("another request for the same requirement: a new ticket", tr.count() == 2)
check("lost fault spec parses", faults.parse("create_test_ticket:lost*1")[0].kind == "lost")

# --- the terminal confirmer
def cli(answer, interactive=True):
    out = io.StringIO()
    asked = []

    def ask(prompt):
        asked.append(prompt)
        if answer is EOFError:
            raise EOFError
        return answer

    d = CliConfirmer(ask=ask, out=out, interactive=interactive)("create_test_ticket", GOOD)
    return d, out.getvalue(), asked


for ans, ok in [("y", True), ("Yes", True), ("так", True), ("т", True), ("", False), ("n", False), ("yep", False), (EOFError, False)]:
    d, _, _ = cli(ans)
    check(f"cli: answer {ans!r} -> {'approve' if ok else 'decline'}", d.approved is ok and d.by == "user")
d, shown, asked = cli("y", interactive=False)
check("cli: no terminal -> declined without asking", not d.approved and asked == [] and d.by == "default")
d, shown, _ = cli("n")
check("cli: the preview lists the tool and every argument and step",
      "create_test_ticket" in shown and GOOD["requirement_ref"] in shown and "2. Request a third remote day" in shown)
check("preview: one line per argument", preview("t", {"a": 1, "b": "x"}).splitlines()[1:] == ["  a: 1", "  b: x"])

print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'all checks passed'}")
sys.exit(1 if FAILED else 0)
