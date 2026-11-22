"""Checks of the tracker MCP server through a real MCP client, in-process and over stdio (no network, no model):
python tests/test_mcp_server.py"""
import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp import Client, StdioServerParameters

from mcp_server.seed import seed
from mcp_server.tracker_server import make_server
from tools.tracker import Tracker

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


tmp = tempfile.TemporaryDirectory()
DB = Path(tmp.name) / "tracker.db"
tr = Tracker(DB)
OWN = dict(doc_id="remote_work_policy", requirement_ref="remote_work_policy#0000", title="Remote days limit",
           steps=["Request a third remote day"], expected="Rejected: at most two days")
own, _ = tr.create(**OWN, key="own-1")                                          # TC-0001, hr-policy-qa
own2, _ = tr.create(**{**OWN, "requirement_ref": "remote_work_policy#0002", "title": "VPN on public Wi-Fi"}, key="own-2")
seed(tr)                                                                         # TC-0003, TC-0004 of payments-qa
tr.close()


def text(r):
    return "".join(getattr(c, "text", "") for c in r.content)


async def call(server, tool, args):
    async with Client(server) as c:
        r = await c.call_tool(tool, args)
        return r.is_error, text(r)


async def main():
    srv = make_server(DB, "hr-policy-qa", "reader")

    # --- the tools the server offers
    async with Client(srv) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        instructions = c.instructions
    check("tools: list_test_cases and get_test_case, nothing else", sorted(tools) == ["get_test_case", "list_test_cases"])
    check("tools: both marked read-only and not destructive",
          all(t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools.values()))
    check("tools: argument schemas with patterns and limits come from the server",
          tools["get_test_case"].input_schema["properties"]["ticket"]["pattern"].startswith("^TC-")
          and tools["list_test_cases"].input_schema["properties"]["limit"]["maximum"] == 50)
    check("instructions name the team of the connection", "hr-policy-qa" in (instructions or ""))

    # --- reading own rows
    err, out = await call(srv, "list_test_cases", {})
    data = json.loads(out)
    check("list: only the 2 rows of our team, newest first", not err and data["total"] == 2
          and [x["ticket"] for x in data["test_cases"]] == ["TC-0002", "TC-0001"] and data["team"] == "hr-policy-qa")
    check("list: no steps in the list", "steps" not in data["test_cases"][0])
    err, out = await call(srv, "list_test_cases", {"requirement_ref": "remote_work_policy#0000"})
    check("list: filter by requirement", [x["ticket"] for x in json.loads(out)["test_cases"]] == ["TC-0001"])
    err, out = await call(srv, "list_test_cases", {"doc_id": "2007_e_store"})
    check("list: another team's document gives 0 rows (their rows are invisible, not counted)",
          not err and json.loads(out)["total"] == 0)
    err, out = await call(srv, "get_test_case", {"ticket": "TC-0001"})
    d = json.loads(out)
    check("get: own test case with steps and expected result", not err and d["steps"] == OWN["steps"] and d["expected"] == OWN["expected"])

    # --- 403 and 404
    err, out = await call(srv, "get_test_case", {"ticket": "TC-0003"})
    check("get: another team's test case -> FORBIDDEN (403)", err and "FORBIDDEN (403)" in out)
    check("get 403: tells the model not to work around it", "do not retry with other tools or parameters" in out)
    check("get 403: the owner team is not revealed", "payments-qa" not in out)
    err, out = await call(srv, "list_test_cases", {"team_filter": "payments-qa"})
    check("list: asking for another team -> FORBIDDEN (403)", err and "FORBIDDEN (403)" in out)
    err, out = await call(srv, "list_test_cases", {"team_filter": "hr-policy-qa"})
    check("list: asking for the own team is fine", not err)
    err, out = await call(srv, "get_test_case", {"ticket": "TC-0099"})
    check("get: unknown ticket -> NOT_FOUND (404)", err and "NOT_FOUND (404)" in out)

    # --- the other team sees the opposite
    pay = make_server(DB, "payments-qa", "reader")
    err, out = await call(pay, "get_test_case", {"ticket": "TC-0003"})
    check("payments-qa reads its own TC-0003", not err and json.loads(out)["team"] == "payments-qa")
    err, out = await call(pay, "get_test_case", {"ticket": "TC-0001"})
    check("payments-qa cannot read our TC-0001", err and "FORBIDDEN (403)" in out)

    # --- input validation: nothing from the caller reaches SQL or the file system as text
    for tool, args, why in [
        ("get_test_case", {"ticket": "TC-0001; DROP TABLE test_cases"}, "SQL in a ticket"),
        ("get_test_case", {"ticket": "1 OR 1=1"}, "a SQL condition"),
        ("list_test_cases", {"doc_id": "x' OR '1'='1"}, "SQL in doc_id"),
        ("list_test_cases", {"doc_id": "../../etc/passwd"}, "a file path"),
        ("list_test_cases", {"requirement_ref": "remote_work_policy"}, "a ref without #nnnn"),
        ("list_test_cases", {"team_filter": "Payments QA!"}, "a malformed team"),
        ("list_test_cases", {"limit": 1000}, "limit above 50"),
        ("list_test_cases", {"limit": 0}, "limit 0"),
    ]:
        err, out = await call(srv, tool, args)
        check(f"validation: {why} is rejected by the schema", err and "validation error" in out)
    check("validation: the table is still there", sqlite3.connect(DB).execute("SELECT COUNT(*) FROM test_cases").fetchone()[0] == 4)

    # --- read-only: the connection cannot write even if a query tried
    import mcp_server.tracker_server as ts
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        con.execute("DELETE FROM test_cases")
        check("read-only: a write on the server's kind of connection fails", False)
    except sqlite3.OperationalError:
        check("read-only: a write on the server's kind of connection fails", True)
    check("read-only: the server never uses SELECT *", "SELECT *" not in Path(ts.__file__).read_text())

    # --- no database yet: a clear 503, not a crash or an empty answer
    empty = make_server(Path(tmp.name) / "missing.db", "hr-policy-qa", "reader")
    err, out = await call(empty, "list_test_cases", {})
    check("missing database -> UNAVAILABLE (503)", err and "UNAVAILABLE (503)" in out)
    check("missing database: the server does not create it", not (Path(tmp.name) / "missing.db").exists())

    # --- identity: unknown team or role -> the server does not start
    for team, role in [("unknown-team", "reader"), ("auditors", "writer")]:
        try:
            make_server(DB, team, role)
            check(f"identity: {team}/{role} refused", False)
        except SystemExit as e:
            check(f"identity: {team}/{role} refused", team in str(e))

    # --- the real entry point over stdio (as the agent and other MCP clients start it)
    env = {**os.environ, "TRACKER_TEAM": "hr-policy-qa", "TRACKER_ROLE": "reader", "TRACKER_DB": str(DB)}
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.tracker_server"], env=env, cwd=str(ROOT))
    async with Client(params) as c:
        names = sorted(t.name for t in (await c.list_tools()).tools)
        r = await c.call_tool("get_test_case", {"ticket": "TC-0003"})
    check("stdio: the server starts as a subprocess and lists its tools", names == ["get_test_case", "list_test_cases"])
    check("stdio: the 403 arrives over the protocol", r.is_error and "FORBIDDEN (403)" in text(r))
    bad = subprocess.run([sys.executable, "-m", "mcp_server.tracker_server"], cwd=ROOT, capture_output=True, text=True,
                         env={**env, "TRACKER_TEAM": "intruders"}, timeout=60, stdin=subprocess.DEVNULL)
    check("stdio: an unknown team stops the server with a message", bad.returncode != 0 and "unknown team" in bad.stderr)


asyncio.run(main())
tmp.cleanup()
print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'all checks passed'}")
sys.exit(1 if FAILED else 0)
