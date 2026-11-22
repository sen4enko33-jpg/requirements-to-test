"""Checks of the agent loop, limits, tool errors and trace with a scripted model (no network, no key):
python tests/test_loop.py"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel

from agent.limits import Limits
from agent.llm import ChatResult, ToolCall
from agent.loop import run_agent
from agent.trace import Trace
from tools.echo import ECHO
from tools.registry import Tool, ToolRegistry

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


class ScriptedModel:
    """Returns the prepared results one by one (the last one again when the script ends) and records what it was sent."""
    name = "scripted"

    def __init__(self, *results, on_call=None):
        self.results, self.calls, self.on_call = list(results), [], on_call

    def chat(self, messages, tools, timeout_s=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools, "timeout_s": timeout_s})
        if self.on_call:
            self.on_call()
        i = min(len(self.calls) - 1, len(self.results) - 1)
        return self.results[i]


def answer(text, tin=100, tout=10, cost=0.001):
    return ChatResult(text, tokens_in=tin, tokens_out=tout, cost_usd=cost)


def calls(*specs, text=None, tin=100, tout=10, cost=0.001):
    """specs: (name, json arguments) pairs -> a model result that asks for these tool calls."""
    return ChatResult(text, [ToolCall(f"c{i}", n, a) for i, (n, a) in enumerate(specs)], tokens_in=tin, tokens_out=tout,
                      cost_usd=cost)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


SYSTEM = "system prompt"
LIM = Limits(max_steps=5, max_tokens_total=100000, max_cost_usd=1.0, request_timeout_s=100, tool_timeout_s=5)
TOOLS = ToolRegistry([ECHO])


def run(model, limits=LIM, tools=TOOLS, trace=None, clock=None):
    return run_agent("question?", model, tools, limits, SYSTEM, trace or Trace(), clock=clock)


# --- a plain answer, no tools
m = ScriptedModel(answer("Hi! I answer questions about requirements documents."))
r = run(m)
check("no tools: answered in one step", r.stop_reason == "answered" and r.complete and r.usage["steps"] == 1)
check("no tools: the answer is the model text", r.answer.startswith("Hi!") and r.tool_calls == [])
check("no tools: the model gets system + user and the tool schemas",
      [x["role"] for x in m.calls[0]["messages"]] == ["system", "user"] and m.calls[0]["tools"][0]["function"]["name"] == "echo")

# --- one tool call, then an answer
m = ScriptedModel(calls(("echo", '{"text": "ping"}')), answer("The tool said ping."))
r = run(m)
check("tool: answered in two steps", r.stop_reason == "answered" and r.usage["steps"] == 2)
second = m.calls[1]["messages"]
check("tool: the assistant tool call and the tool result go back to the model",
      second[-2]["role"] == "assistant" and second[-2]["tool_calls"][0]["function"]["name"] == "echo"
      and second[-1] == {"role": "tool", "tool_call_id": "c0", "content": '{"echo": "ping"}'})
check("tool: recorded in the result",
      r.tool_calls == [{"step": 1, "name": "echo", "args": {"text": "ping"}, "ok": True, "error_kind": None, "attempts": 1,
                         "confirmed": None}])

# --- two tool calls in one step: both get a result
m = ScriptedModel(calls(("echo", '{"text": "a"}'), ("echo", '{"text": "b"}')), answer("a and b"))
r = run(m)
check("two calls in one step: both run and both results are sent back",
      len(r.tool_calls) == 2 and [x["tool_call_id"] for x in m.calls[1]["messages"] if x["role"] == "tool"] == ["c0", "c1"])

# --- step limit: a model that never stops calling tools
m = ScriptedModel(calls(("echo", '{"text": "again"}'), text="Let me check once more."))
r = run(m, Limits(max_steps=3, max_tokens_total=100000, max_cost_usd=1.0, request_timeout_s=100, tool_timeout_s=5))
check("max_steps: stopped after exactly 3 model calls", r.stop_reason == "max_steps" and len(m.calls) == 3 and not r.complete)
check("max_steps: partial result says why and what was collected",
      "step limit" in r.answer and "echo" in r.answer and "again" in r.answer and "once more" in r.answer)

# --- cost budget
m = ScriptedModel(calls(("echo", '{"text": "x"}'), cost=0.01))
r = run(m, Limits(max_steps=50, max_tokens_total=10**9, max_cost_usd=0.025, request_timeout_s=100, tool_timeout_s=5))
check("budget_cost: stopped when 0.03 >= 0.025 USD were spent (3 calls)", r.stop_reason == "budget_cost" and len(m.calls) == 3)
check("budget_cost: usage reports the cost", abs(r.usage["cost_usd"] - 0.03) < 1e-9)

# --- token budget
m = ScriptedModel(calls(("echo", '{"text": "x"}'), tin=900, tout=100, cost=0))
r = run(m, Limits(max_steps=50, max_tokens_total=2500, max_cost_usd=1.0, request_timeout_s=100, tool_timeout_s=5))
check("budget_tokens: stopped after 3 calls of 1000 tokens (limit 2500)", r.stop_reason == "budget_tokens" and len(m.calls) == 3)

# --- request timeout (a fake clock: every model call takes 40 s)
clock = FakeClock()
m = ScriptedModel(calls(("echo", '{"text": "x"}')), on_call=lambda: setattr(clock, "t", clock.t + 40))
r = run(m, Limits(max_steps=50, max_tokens_total=10**9, max_cost_usd=1.0, request_timeout_s=100, tool_timeout_s=5), clock=clock)
check("timeout: stopped after 3 calls of 40 s (limit 100 s)", r.stop_reason == "timeout" and len(m.calls) == 3)
check("timeout: the model gets the remaining time as its call timeout", [c["timeout_s"] for c in m.calls] == [100, 60, 20])

# --- tool errors do not stop the agent; the model gets a text it can act on
m = ScriptedModel(calls(("echo", '{}')), calls(("echo", '{"text": "fixed"}')), answer("fixed"))
r = run(m)
err = [x for x in m.calls[1]["messages"] if x["role"] == "tool"][0]["content"]
check("invalid args: the error goes to the model as text", err.startswith("ERROR: invalid_args:") and "text" in err)
check("invalid args: the model fixed the call and answered", r.stop_reason == "answered" and [c["ok"] for c in r.tool_calls] == [False, True])

for raw, kind in [("{not json", "bad_json"), ('{"text": ""}', "invalid_args")]:
    out = TOOLS.execute("echo", raw, 5)
    check(f"{kind}: {raw!r} -> ERROR: {kind}", not out.ok and out.error_kind == kind and out.content.startswith(f"ERROR: {kind}:"))
out = TOOLS.execute("delete_everything", "{}", 5)
check("unknown tool: ERROR with the list of tools", out.error_kind == "unknown_tool" and "echo" in out.content)


class NoArgs(BaseModel):
    pass


def boom(_):
    raise RuntimeError("database is down")


def slow(_):
    time.sleep(2)
    return "late"


reg = ToolRegistry([Tool("boom", "fails", NoArgs, boom), Tool("slow", "slow", NoArgs, slow)], sleep=lambda s: None)
out = reg.execute("boom", "{}", 5)
check("exception in a tool: ERROR: tool_error with the message", out.error_kind == "tool_error" and "database is down" in out.content)
t0 = time.perf_counter()
out = reg.execute("slow", "{}", 0.3)
check("slow tool: ERROR: timeout after the tool timeout (3 attempts of 0.3 s), not after the tool",
      out.error_kind == "timeout" and out.attempts == 3 and time.perf_counter() - t0 < 1.5)
check("no time left: the tool is not started", reg.execute("slow", "{}", 0).error_kind == "timeout")
m = ScriptedModel(calls(("boom", "{}")), answer("The service is unavailable."))
r = run(m, tools=reg)
check("exception in a tool: the agent keeps running and answers", r.stop_reason == "answered" and r.tool_calls[0]["error_kind"] == "tool_error")
try:
    ToolRegistry([ECHO, ECHO])
    check("registry: duplicate name is rejected", False)
except ValueError:
    check("registry: duplicate name is rejected", True)

# --- model failure
m = ScriptedModel(calls(("echo", '{"text": "x"}')), ChatResult(None, error="APIConnectionError: down"))
r = run(m)
check("model error: stop_reason model_error, partial result with what was collected",
      r.stop_reason == "model_error" and not r.complete and "did not answer" in r.answer and "echo" in r.answer)

# --- trace: a JSON line per event, the stop reason at the end
with tempfile.TemporaryDirectory() as d:
    m = ScriptedModel(calls(("echo", '{"text": "x"}')))
    r = run(m, Limits(max_steps=2, max_tokens_total=100000, max_cost_usd=1.0, request_timeout_s=100, tool_timeout_s=5), trace=Trace(d))
    events = Trace.read(r.trace_path)
    check("trace: start, model, tool, model, tool, stop", [e["event"] for e in events] == ["start", "model", "tool", "model", "tool", "stop"])
    check("trace: the stop event has the reason and the usage",
          events[-1]["stop_reason"] == "max_steps" and events[-1]["steps"] == 2 and "cost_usd" in events[-1])
    check("trace: the limits are recorded at the start", events[0]["limits"]["max_steps"] == 2 and events[0]["tools"] == ["echo"])
    check("trace: every line has the run id", {e["run_id"] for e in events} == {r.run_id})

# --- schema of a tool for the model
s = ECHO.schema()
check("schema: function with a description and JSON Schema parameters",
      s["type"] == "function" and s["function"]["parameters"]["required"] == ["text"] and "only" in s["function"]["description"])

# --- limits from config.yaml
import yaml
cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text())
lim = Limits.from_config(cfg["limits"])
check("config: limits are read", lim.max_steps == 8 and lim.max_cost_usd == 0.02 and lim.tool_timeout_s == 20)

print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'all checks passed'}")
sys.exit(1 if FAILED else 0)
