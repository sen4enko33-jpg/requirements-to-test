"""Checks of fault injection, retries with backoff and the output schemas (no network, no models):
python tests/test_faults.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel

from agent.limits import Limits
from agent.llm import ChatResult, ToolCall
from agent.loop import run_agent
from agent.trace import Trace
from tools import faults
from tools.corpus import Corpus
from tools.corpus_tools import make_corpus_tools
from tools.registry import RetryPolicy, Tool, ToolRegistry, ToolUnavailable

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


class NoArgs(BaseModel):
    pass


class Out(BaseModel):
    items: list[dict]


class Item(BaseModel):
    id: str
    value: int


class ItemsOut(BaseModel):
    items: list[Item]


def make(safe=True, spec=None, fn=None):
    """A registry with one tool `t` and recorded pauses instead of real sleeps."""
    pauses = []
    calls = {"n": 0}

    def ok(_):
        calls["n"] += 1
        return {"items": [{"id": "a", "value": 1}]}

    reg = ToolRegistry([Tool("t", "test tool", NoArgs, fn or ok, safe=safe, side_effect=not safe, output_model=ItemsOut)],
                       RetryPolicy(max_attempts=3, backoff_s=0.5, backoff_max_s=4), sleep=pauses.append)
    if spec:
        faults.apply(reg, spec)
    return reg, pauses, calls


# --- parsing the FAULTS spec
fs = faults.parse("timeout, search_corpus:503*2,schema")
check("parse: three items with tool, kind and count",
      [(f.tool, f.kind, f.times) for f in fs] == [(None, "timeout", None), ("search_corpus", "503", 2), (None, "schema", None)])
check("parse: empty spec -> no faults", faults.parse("") == [] and faults.parse(None) == [])
for bad in ("500", "search_corpus:", "503*x", "rm -rf"):
    try:
        faults.parse(bad)
        check(f"parse: {bad!r} is rejected", False)
    except ValueError:
        check(f"parse: {bad!r} is rejected", True)
try:
    faults.apply(make()[0], "serch_corpus:503")
    check("apply: a typo in the tool name is an error, not a silent no-op", False)
except ValueError as e:
    check("apply: a typo in the tool name is an error, not a silent no-op", "serch_corpus" in str(e))

# --- no faults: one attempt, the answer passes the output schema
reg, pauses, calls = make()
out = reg.execute("t", "{}", 5)
check("no fault: ok in one attempt, no pause", out.ok and out.attempts == 1 and pauses == [] and calls["n"] == 1)

# --- 503 once: the retry recovers
reg, pauses, calls = make(spec="503*1")
out = reg.execute("t", "{}", 5)
check("503*1: retried once and recovered", out.ok and out.attempts == 2 and calls["n"] == 1)
check("503*1: one backoff pause of 0.5 s", pauses == [0.5])
check("503*1: the failed attempt is kept for the trace", out.errors == ["unavailable: t: [fault] HTTP 503 Service Unavailable"])

# --- 503 always: three attempts with growing pauses, then an honest error
reg, pauses, calls = make(spec="503")
out = reg.execute("t", "{}", 5)
check("503: three attempts, pauses 0.5 and 1.0 s, the tool never answered",
      not out.ok and out.attempts == 3 and pauses == [0.5, 1.0] and calls["n"] == 0)
check("503: ERROR: unavailable tells the model not to answer from memory",
      out.error_kind == "unavailable" and out.content.startswith("ERROR: unavailable:") and "do not answer from memory" in out.content
      and "after 3 attempt(s)" in out.content)

# --- 429: Retry-After wins over a shorter backoff
reg, pauses, _ = make(spec="429")
out = reg.execute("t", "{}", 5)
check("429: rate_limited, pauses follow Retry-After 1 s", out.error_kind == "rate_limited" and pauses == [1.0, 1.0])

# --- timeout
reg, pauses, _ = make(spec="timeout")
out = reg.execute("t", "{}", 5)
check("timeout: retried, then ERROR: timeout", out.error_kind == "timeout" and out.attempts == 3 and len(pauses) == 2)

# --- a tool that changes data is never retried
reg, pauses, _ = make(safe=False, spec="503")
out = reg.execute("t", "{}", 5)
check("unsafe tool + 503: one attempt only, no pause", out.attempts == 1 and pauses == [] and out.error_kind == "unavailable")
check("unsafe tool + 503: the error says why there was no retry", "not retried: the tool changes data" in out.content)

# --- retries stop when the request runs out of time
reg, pauses, _ = make(spec="503")
out = reg.execute("t", "{}", 5, time_left_s=0.7)
check("little time left: no pause that would pass the deadline", out.attempts == 2 and pauses == [0.5])

# --- changed format: the output schema catches it, no retry, the field is named
reg, pauses, calls = make(spec="schema")
out = reg.execute("t", "{}", 5)
check("schema: ERROR: bad_output, not retried", out.error_kind == "bad_output" and out.attempts == 1 and pauses == [])
check("schema: the error names the missing field", "items.0.id" in out.content and "Field required" in out.content)
check("schema: the changed answer never reaches the model", '"id_v2"' not in out.content)
check("schema: the error says it is a service failure, not a missing answer", "failure of the service" in out.content)
reg, _, _ = make(fn=lambda _: {"items": [{"x": 1}] * 5})
out = reg.execute("t", "{}", 5)
check("bad_output: at most 3 field errors listed, the rest counted", out.content.count("Field required") == 3 and "and 7 more" in out.content)

# --- a real API that drops a field (not via faults)
reg, _, _ = make(fn=lambda _: {"items": [{"id": "a"}]})
out = reg.execute("t", "{}", 5)
check("missing field from the service: bad_output names it", out.error_kind == "bad_output" and "items.0.value" in out.content)
reg, _, _ = make(fn=lambda _: {"items": [{"id": "a", "value": None}]})
check("null instead of a number: bad_output, not a silent None", reg.execute("t", "{}", 5).error_kind == "bad_output")

# --- errors that are not retried
reg, pauses, _ = make(fn=lambda _: (_ for _ in ()).throw(RuntimeError("bug")))
out = reg.execute("t", "{}", 5)
check("tool_error: not retried", out.error_kind == "tool_error" and out.attempts == 1 and pauses == [])
check("invalid_args: rejected before running", make()[0].execute("t", "not json", 5).attempts == 0)

# --- the corpus tools: faults on one tool, schema fault on real data
corpus = Corpus()
pol = [c for c in corpus.chunks if c.startswith("remote_work_policy#")]


class FakeRetriever:
    def search(self, query, k, mode, filters):
        return [{**corpus.chunks[pol[0]], "score": 5.0}]


corpus._retriever = FakeRetriever()
reg = ToolRegistry(make_corpus_tools(corpus, floor=None), sleep=lambda s: None)
faults.apply(reg, "search_corpus:schema")
out = reg.execute("search_corpus", json.dumps({"query": "remote days"}), 5)
check("corpus schema fault: results.0.ref renamed -> bad_output naming results.0.ref",
      out.error_kind == "bad_output" and "results.0.ref" in out.content)
check("corpus schema fault: other tools still work", reg.execute("list_documents", "{}", 5).ok)
check("corpus tools: normal answers pass their output schemas",
      ToolRegistry(make_corpus_tools(corpus, floor=None)).execute("search_corpus", json.dumps({"query": "remote days"}), 5).ok)

# --- in the loop: the agent reports the outage, the trace keeps the attempts
reg, _, _ = make(spec="503")


class Scripted:
    name = "scripted"

    def __init__(self, *results):
        self.results, self.seen = list(results), []

    def chat(self, messages, tools, timeout_s=None):
        self.seen.append(messages)
        return self.results[min(len(self.seen) - 1, len(self.results) - 1)]


m = Scripted(ChatResult(None, [ToolCall("c0", "t", "{}")]), ChatResult("The search service is unavailable right now."))
trace = Trace()
r = run_agent("q", m, reg, Limits(), "sys", trace)
tool_ev = trace.of("tool")[0]
check("loop: the model gets the unavailable error as the tool result",
      m.seen[1][-1]["content"].startswith("ERROR: unavailable:"))
check("loop: trace keeps attempts and every attempt error",
      tool_ev["attempts"] == 3 and len(tool_ev["attempt_errors"]) == 3 and tool_ev["error_kind"] == "unavailable")
check("loop: tool_calls in the result carry the attempts", r.tool_calls[0]["attempts"] == 3 and r.stop_reason == "answered")

print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'all checks passed'}")
sys.exit(1 if FAILED else 0)
