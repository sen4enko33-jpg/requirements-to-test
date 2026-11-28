"""Checks of the agent as an MCP client (tools/mcp_tools.py): the server's tools in the registry and in the agent loop,
with the same validation, retries, faults, limits and trace as the local tools (no network, no model):
python tests/test_mcp_tools.py"""
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mcp_types as mt
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from agent.confirm import ScriptedConfirmer
from agent.limits import Limits
from agent.llm import ChatResult, ToolCall
from agent.loop import run_agent
from agent.trace import Trace
from mcp_server.seed import seed
from mcp_server.tms_server import make_server
from tools import faults
from tools.echo import ECHO
from tools.corpus import Corpus
from tools.corpus_tools import make_corpus_tools
from tools.mcp_tools import McpConnection, McpError, McpTmsStore, mcp_tools, open_server, stdio_params
from tools.session import Session
from tools.ticket_tool import make_ticket_tool
from tools.registry import RetryPolicy, ToolRegistry
from tools.tms import Tms

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


class ScriptedModel:
    """Returns the prepared results one by one (as in tests/test_loop.py) and records what it was sent."""
    name = "scripted"

    def __init__(self, *results):
        self.results, self.calls = list(results), []

    def chat(self, messages, tools, timeout_s=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        return self.results[min(len(self.calls) - 1, len(self.results) - 1)]


def answer(text):
    return ChatResult(text, tokens_in=100, tokens_out=10, cost_usd=0.001)


def calls(*specs):
    return ChatResult(None, [ToolCall(f"c{i}", n, a) for i, (n, a) in enumerate(specs)], tokens_in=100, tokens_out=10,
                      cost_usd=0.001)

tmp = tempfile.TemporaryDirectory()
DB = Path(tmp.name) / "tms.db"
tr = Tms(DB)
tr.create("remote_work_policy", "remote_work_policy#0000", "Remote days limit", ["Request a third remote day"],
          "Rejected: at most two days", key="own-1")                       # TC-0001, our team
seed(tr)                                                                     # TC-0002, TC-0003 of payments-qa
CFG = {"module": "mcp_server.tms_server", "env": {"TMS_TEAM": "hr-policy-qa", "TMS_ROLE": "reader"}}
LIM = Limits(max_steps=5, max_tokens_total=100000, max_cost_usd=1.0, request_timeout_s=60, tool_timeout_s=10)
pauses = []


def registry(conn, *more, spec=None):
    reg = ToolRegistry([*more, *mcp_tools(conn)], RetryPolicy(max_attempts=3, backoff_s=0.01), sleep=pauses.append)
    if spec:
        faults.apply(reg, spec)
    return reg


# --- in-process: the tools as the server describes them
with McpConnection(make_server(DB, "hr-policy-qa", "reader")) as conn:
    reg = registry(conn)
    check("tools from tools/list: list_test_cases, get_test_case", sorted(reg.tools) == ["get_test_case", "list_test_cases"])
    check("read-only on the server -> safe, no side effect (no confirmation, retried)",
          all(t.safe and not t.side_effect for t in reg.tools.values()))
    check("server name and version in the tool version (written to the trace)",
          reg.tools["get_test_case"].version == "mcp:tms@1.3")
    sch = {s["function"]["name"]: s["function"] for s in reg.schemas()}
    check("the model gets the server's argument schema (pattern, maximum)",
          sch["get_test_case"]["parameters"]["properties"]["ticket"]["pattern"].startswith("^TC-")
          and sch["list_test_cases"]["parameters"]["properties"]["limit"]["maximum"] == 50)
    check("the description is the server's, without docstring indentation",
          sch["get_test_case"]["description"].startswith("Returns one test case") and "\n    " not in sch["get_test_case"]["description"])
    check("instructions of the server are kept", "hr-policy-qa" in (conn.instructions or ""))

    o = reg.execute("list_test_cases", "{}", 5)
    check("list: our team's rows only", o.ok and [x["ticket"] for x in json.loads(o.content)["test_cases"]] == ["TC-0001"])
    o = reg.execute("get_test_case", '{"ticket": "TC-0001"}', 5)
    check("get: own test case with steps", o.ok and json.loads(o.content)["steps"] == ["Request a third remote day"])

    o = reg.execute("get_test_case", '{"ticket": "TC-0002"}', 5)
    check("403 -> ERROR: forbidden, one attempt (a permission is not retried)",
          not o.ok and o.error_kind == "forbidden" and o.attempts == 1 and o.content.startswith("ERROR: forbidden: FORBIDDEN (403)"))
    check("403: the server's advice reaches the model, the library prefix does not",
          "do not retry" in o.content and "Error executing tool" not in o.content)
    o = reg.execute("get_test_case", '{"ticket": "TC-0099"}', 5)
    check("404 -> ERROR: not_found, not retried", o.error_kind == "not_found" and o.attempts == 1 and "NOT_FOUND (404)" in o.content)
    o = reg.execute("get_test_case", '{"ticket": "TC-1; DROP TABLE test_cases"}', 5)
    check("bad argument -> invalid_args here, before any call to the server", o.error_kind == "invalid_args" and o.attempts == 0
          and "does not match" in o.content and "Value error" not in o.content)
    o = reg.execute("list_test_cases", '{"limit": 500, "doc_id": "../x"}', 5)
    check("several bad arguments are all named", o.error_kind == "invalid_args" and "limit" in o.content and "doc_id" in o.content)
    o = reg.execute("list_test_cases", '{"limit": 2}', 5)
    check("optional arguments left out are not sent as null", o.ok)

    # --- faults: FAULTS works for the MCP tools as for the local ones
    reg = registry(conn, spec="get_test_case:503*1")
    pauses.clear()
    o = reg.execute("get_test_case", '{"ticket": "TC-0001"}', 5)
    check("FAULTS 503*1: retried and recovered", o.ok and o.attempts == 2 and len(pauses) == 1)
    o = registry(conn, spec="list_test_cases:schema").execute("list_test_cases", "{}", 5)
    check("FAULTS schema: the answer breaks the server's output schema -> bad_output",
          o.error_kind == "bad_output" and "ticket" in o.content)
    o = registry(conn, spec="timeout").execute("list_test_cases", "{}", 5)
    check("FAULTS timeout on every MCP call: 3 attempts, then the service is down",
          o.error_kind == "timeout" and o.attempts == 3 and "unavailable right now" in o.content)

# --- a real 503 of the server (no database) is retried
with McpConnection(make_server(Path(tmp.name) / "none.db", "hr-policy-qa", "reader")) as conn:
    o = registry(conn).execute("list_test_cases", "{}", 5)
    check("server UNAVAILABLE (503) -> unavailable after 3 attempts", o.error_kind == "unavailable" and o.attempts == 3
          and "UNAVAILABLE (503)" in o.content)

# --- a slow server and a server that is gone
slow = MCPServer("slow")


@slow.tool(annotations=mt.ToolAnnotations(readOnlyHint=True))
async def nap(seconds: float) -> str:
    """Sleeps."""
    import anyio
    await anyio.sleep(seconds)
    return "awake"


@slow.tool()
def boom() -> str:
    """Always fails."""
    raise ToolError("something broke")


with McpConnection(slow, call_timeout_s=0.5) as conn:
    reg = registry(conn)
    check("a tool without readOnlyHint -> side effect (needs a confirmation), not retried",
          reg.tools["boom"].side_effect and not reg.tools["boom"].safe)
    t0 = time.perf_counter()
    o = reg.execute("nap", '{"seconds": 5}', 5)
    took = time.perf_counter() - t0
    check("a call slower than call_timeout_s -> timeout, retried, then given up", o.error_kind == "timeout" and o.attempts == 3)
    check(f"... without waiting for the slow tool ({took:.1f} s)", took < 4)
    o = reg.execute("nap", '{"seconds": 0}', 5)
    check("the connection still works after timeouts", o.ok and json.loads(o.content) == {"result": "awake"})
    o = reg.execute("boom", "{}", 5)
    check("another server error -> tool_error", o.error_kind == "tool_error" and "something broke" in o.content)
check("closed after the with block", conn.closed)
o = ToolRegistry(mcp_tools(conn), RetryPolicy(max_attempts=2, backoff_s=0.01), sleep=pauses.append).execute(
    "nap", '{"seconds": 0}', 5)
check("a call after the server is gone -> unavailable, not a crash", o.error_kind == "unavailable" and "not running" in o.content)

# --- the agent loop: the MCP tools next to a local tool, in the trace
with McpConnection(make_server(DB, "hr-policy-qa", "reader")) as conn:
    reg = registry(conn, ECHO)
    model = ScriptedModel(calls(("get_test_case", '{"ticket": "TC-0002"}'), ("get_test_case", '{"ticket": "TC-0001"}')),
                          answer("TC-0002 is not accessible; TC-0001 checks the remote days limit."))
    tr_ = Trace()
    r = run_agent("show TC-0001 and TC-0002", model, reg, LIM, "sys", tr_, confirm=ScriptedConfirmer())
    tools_sent = [t["function"]["name"] for t in model.calls[0]["tools"]]
    check("agent: the model is offered the MCP tools with the local ones", tools_sent == ["echo", "list_test_cases", "get_test_case"])
    check("agent: no confirmation was asked for read-only MCP tools", not tr_.of("confirm"))
    tev = tr_.of("tool")
    check("agent trace: 403 and success of the MCP calls", [e["error_kind"] for e in tev] == ["forbidden", None])
    start = tr_.of("start")[0]
    check("agent trace: the start lists the MCP tools and their version",
          start["tool_versions"].get("get_test_case") == "mcp:tms@1.3")
    check("agent: answered after the two calls", r.complete and len(r.tool_calls) == 2)

# --- writing through the server (2.3): create_test_ticket -> McpTmsStore -> create_test_case
corpus = Corpus()
pol = [c for c in corpus.chunks if c.startswith("remote_work_policy#")]


class FakeRetriever:
    def search(self, query, k, mode, filters):
        return [{**corpus.chunks[pol[0]], "score": 5.0}]


corpus._retriever = FakeRetriever()
TICKET = json.dumps({"requirement_ref": pol[0], "title": "Remote days limit after probation",
                     "steps": ["Log in as an employee after probation", "Request a third remote day"],
                     "expected": "The request is rejected: at most two remote days per week."})


def ticket_registry(conn, request="Create a test case for the remote days limit", spec=None):
    session = Session(run_id="run-mcp", request=request)
    reg = ToolRegistry(make_corpus_tools(corpus, floor=None, session=session) +
                       [make_ticket_tool(McpTmsStore(conn), corpus, session)] +
                       (mcp_tools(conn, hidden=("create_test_case",)) if conn else []),
                       RetryPolicy(max_attempts=3, backoff_s=0.01), sleep=pauses.append)
    if spec:
        faults.apply(reg, spec)
    reg.execute("search_corpus", '{"query": "remote days"}', 5)        # the agent has read the requirement
    return reg


with McpConnection(make_server(DB, "hr-policy-qa", "writer")) as conn:
    reg = ticket_registry(conn)
    check("hidden: the model is not offered create_test_case of the server",
          "create_test_case" not in reg.tools and "create_test_ticket" in reg.tools and "get_test_case" in reg.tools)
    check("create_test_ticket stays a side effect (confirmation in the loop, not retried)",
          reg.tools["create_test_ticket"].side_effect and not reg.tools["create_test_ticket"].safe)
    o = reg.execute("create_test_ticket", TICKET, 10)
    d = json.loads(o.content) if o.ok else {}
    check("create_test_ticket writes through the server", o.ok and d.get("created") and d["ticket"] == "TC-0004")
    row = sqlite3.connect(DB).execute("SELECT team, run_id FROM test_cases WHERE id = 4").fetchone()
    check("the row: our team (set by the server) and the run id of the agent", row == ("hr-policy-qa", "run-mcp"))
    o = ticket_registry(conn).execute("create_test_ticket", TICKET, 10)
    check("the same request again -> duplicate, no new row (idempotency on the server)",
          o.ok and json.loads(o.content)["duplicate"] and json.loads(o.content)["ticket"] == "TC-0004")
    o = reg.execute("get_test_case", '{"ticket": "TC-0004"}', 10)
    check("the new test case is readable through get_test_case", o.ok and json.loads(o.content)["steps"][1] == "Request a third remote day")
    o = ticket_registry(conn, request="file the test case, connection breaks", spec="create_test_ticket:lost*1").execute(
        "create_test_ticket", TICKET, 10)
    check("FAULTS lost: written on the server, the agent sees a timeout, not retried", o.error_kind == "timeout" and o.attempts == 1)
    o = ticket_registry(conn, request="file the test case, connection breaks").execute("create_test_ticket", TICKET, 10)
    check("... the repeated request finds it: duplicate, not a second row", o.ok and json.loads(o.content)["duplicate"])
    reg_bad = ticket_registry(conn)
    o = reg_bad.execute("create_test_ticket", TICKET.replace(pol[0], "remote_work_policy#0099"), 10)
    check("an unknown ref is still stopped in the agent, before the server", o.error_kind == "invalid_args" and o.attempts == 0)
n_rows = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM test_cases").fetchone()[0]
check("writes: 2 rows added in all (TC-0004, TC-0005), no duplicates", n_rows == 5)

with McpConnection(make_server(DB, "hr-policy-qa", "reader")) as conn:
    o = ticket_registry(conn, request="create a test case as a reader").execute("create_test_ticket", TICKET, 10)
    check("a reader connection -> forbidden, nothing written", o.error_kind == "forbidden" and "nothing was created" in o.content)
o = ticket_registry(None, request="create a test case, no server").execute("create_test_ticket", TICKET, 10)
check("no server -> unavailable, nothing written past the server", o.error_kind == "unavailable" and "not running" in o.content)
check("... still 5 rows", sqlite3.connect(DB).execute("SELECT COUNT(*) FROM test_cases").fetchone()[0] == 5)

# --- over stdio, as main.py starts it; a server that cannot start
log = Path(tmp.name) / "mcp.log"
conn = open_server({"mcp": {"tms": {**CFG, "log": str(log)}}}, "tms", db=DB, quiet=True)
check("stdio: open_server starts the subprocess", conn is not None and sorted(t.name for t in conn.tools) == ["get_test_case", "list_test_cases"])
o = registry(conn).execute("get_test_case", '{"ticket": "TC-0003"}', 10)
check("stdio: 403 over the protocol", o.error_kind == "forbidden")
conn.close()
check("stdio: the server's log goes to the log file, not to the agent's output", "DENY get_test_case" in log.read_text())
bad = open_server({"mcp": {"tms": {**CFG, "env": {"TMS_TEAM": "intruders"}, "log": str(log)}}}, "tms", db=DB,
                  quiet=True)
check("stdio: a server that refuses to start -> None (the agent runs without it)", bad is None)
check("stdio: ... and the reason is in its log", "unknown team" in log.read_text())
try:
    McpConnection(stdio_params({**CFG, "env": {"TMS_TEAM": "intruders"}}, DB), errlog=log.open("a")).open()
    check("McpConnection.open raises McpError for a server that does not start", False)
except McpError:
    check("McpConnection.open raises McpError for a server that does not start", True)
check("no mcp section -> no connection", open_server({}, "tms") is None)

tr.close()
tmp.cleanup()
print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'all checks passed'}")
sys.exit(1 if FAILED else 0)
