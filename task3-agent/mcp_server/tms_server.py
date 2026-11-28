"""MCP server of the TMS (step 2): reading (2.1) and, for the role writer, creating test cases (2.3).

    TMS_TEAM=hr-policy-qa TMS_ROLE=reader python -m mcp_server.tms_server     # stdio transport

Who calls it: the agent of this repository (it starts the server as a subprocess, see tools/mcp_tools.py), and any other
MCP client - Claude Desktop, an IDE, an agent of another team - with the same command and its own TMS_TEAM.

Restrictions, enforced here and not left to the client or the model:
  - one table only (test_cases) and only fixed, parameterised queries: no SQL, shell or file path comes from a caller;
  - reads open the database read-only (SQLite mode=ro + PRAGMA query_only), so even a bug in a read cannot write;
  - the only write is one fixed INSERT of create_test_case, and only a writer connection has that tool at all (a reader
    does not even see it in tools/list); the team of a new row is the team of the connection, never an argument;
  - create_test_case is idempotent: the client sends an idempotency key, the same key returns the existing row
    (created=false) instead of a duplicate; a key that belongs to another team is a CONFLICT (409) that reveals nothing;
  - every argument is checked by its schema (patterns for doc_id, ref, ticket, team; limits on numbers);
  - a client sees only the rows of its own team; a row or a team filter of another team is FORBIDDEN (403);
  - the team and role must be listed in mcp_server/access.yaml, otherwise the server does not start.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Annotated, Optional

import mcp_types as mt
import yaml
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.tms import Tms  # noqa: E402  - the same table and the same INSERT ... ON CONFLICT DO NOTHING

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "tms.db"
ACCESS = Path(__file__).resolve().parent / "access.yaml"
log = logging.getLogger("tms-mcp")

DOC_ID = r"^[A-Za-z0-9_.-]{1,80}$"
REF = r"^[A-Za-z0-9_.-]{1,80}#\d{4}$"
TICKET = r"^TC-\d{4,6}$"
TEAM = r"^[a-z0-9-]{2,40}$"
COLUMNS = "id, doc_id, requirement_ref, title, steps, expected, created_at, team"   # an explicit list, not all columns: a new column stays private

VERSION = "1.3"          # 1.0: the tools of 2.1; 1.1: answers with an output schema (the client checks them);
                         # 1.2: create_test_case for the role writer; 1.3: renamed test-case-tracker -> tms
KEY = r"^[A-Za-z0-9_.:-]{8,80}$"


class TestCaseSummary(BaseModel):
    ticket: str
    doc_id: str
    requirement_ref: str
    title: str
    created_at: str


class TestCaseList(BaseModel):
    team: str
    total: int
    test_cases: list[TestCaseSummary]


class TestCase(TestCaseSummary):
    team: str
    steps: list[str]
    expected: str


class CreatedTestCase(BaseModel):
    ticket: str
    created: bool                    # False: a test case with this idempotency key existed, nothing was written
    team: str
    doc_id: str
    requirement_ref: str
    title: str


FORBIDDEN = ("FORBIDDEN (403): {what} belongs to another team; team {team} has no access to it. This is a permission "
             "decision, not an error to work around: do not retry with other tools or parameters, tell the user that "
             "access is denied.")


def load_access(path: Path = ACCESS) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["teams"]


def check_identity(team: str, role: str, access: dict) -> None:
    if team not in access:
        raise SystemExit(f"TMS MCP server: unknown team {team!r}; known teams are in {ACCESS.name}")
    if role not in access[team]["roles"]:
        raise SystemExit(f"TMS MCP server: team {team!r} may not connect as {role!r} (allowed: {access[team]['roles']})")


def _ticket(row_id: int) -> str:
    return f"TC-{row_id:04d}"


def make_server(db_path: str | Path, team: str, role: str = "reader", access: dict | None = None) -> MCPServer:
    """The server for one client identity. Tests build it in-process; __main__ builds it from the environment."""
    check_identity(team, role, access if access is not None else load_access())
    db_path = Path(db_path)

    def connect() -> sqlite3.Connection:
        if not db_path.exists():
            raise ToolError("UNAVAILABLE (503): the TMS database does not exist yet; no test cases can be read")
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)       # read-only at the file level
        con.execute("PRAGMA query_only = ON")                              # ... and at the connection level
        con.row_factory = sqlite3.Row
        return con

    server = MCPServer(
        "tms",
        version=VERSION,
        instructions=(f"Test cases of software requirements. You are connected as team {team} ({role}); you see only the "
                      "test cases of your team. Access to another team's test case is denied with FORBIDDEN (403)."),
    )
    read_only = mt.ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    @server.tool(annotations=read_only)
    def list_test_cases(
        doc_id: Annotated[Optional[str], Field(None, pattern=DOC_ID, description="Only test cases of this document.")] = None,
        requirement_ref: Annotated[Optional[str], Field(None, pattern=REF, description="Only test cases of this requirement (a passage ref, e.g. remote_work_policy#0000).")] = None,
        team_filter: Annotated[Optional[str], Field(None, pattern=TEAM, description="Team whose test cases to list; only your own team is allowed. Omit it.")] = None,
        limit: Annotated[int, Field(20, ge=1, le=50, description="At most this many test cases, newest first.")] = 20,
    ) -> TestCaseList:
        """Lists the test cases of your team (ticket, document, requirement, title, creation time; no steps).
        Call it to see which test cases exist for a document or a requirement, for example before creating a new one.
        Use get_test_case for the steps and the expected result of one test case."""
        if team_filter is not None and team_filter != team:
            log.info("DENY list_test_cases team=%s asked for team_filter=%s", team, team_filter)
            raise ToolError(FORBIDDEN.format(what=f"the list of team {team_filter!r}", team=team))
        where, params = ["team = ?"], [team]
        if doc_id:
            where.append("doc_id = ?"); params.append(doc_id)
        if requirement_ref:
            where.append("requirement_ref = ?"); params.append(requirement_ref)
        sql = f"SELECT {COLUMNS} FROM test_cases WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?"   # fixed text, values bound
        with connect() as con:
            rows = con.execute(sql, [*params, limit]).fetchall()
            total = con.execute(f"SELECT COUNT(*) FROM test_cases WHERE {' AND '.join(where)}", params).fetchone()[0]
        log.info("ALLOW list_test_cases team=%s doc_id=%s ref=%s -> %d", team, doc_id, requirement_ref, len(rows))
        return TestCaseList(team=team, total=total, test_cases=[
            TestCaseSummary(ticket=_ticket(r["id"]), doc_id=r["doc_id"], requirement_ref=r["requirement_ref"],
                            title=r["title"], created_at=r["created_at"]) for r in rows])

    @server.tool(annotations=read_only)
    def get_test_case(
        ticket: Annotated[str, Field(pattern=TICKET, description="The ticket number, e.g. TC-0001.")],
    ) -> TestCase:
        """Returns one test case of your team with its steps and expected result.
        A test case of another team is denied with FORBIDDEN (403); an unknown number is NOT_FOUND (404)."""
        with connect() as con:
            r = con.execute(f"SELECT {COLUMNS} FROM test_cases WHERE id = ?", (int(ticket[3:]),)).fetchone()
        if r is None:
            log.info("MISS get_test_case team=%s %s", team, ticket)
            raise ToolError(f"NOT_FOUND (404): there is no test case {ticket}")
        if r["team"] != team:
            log.info("DENY get_test_case team=%s %s (owner %s)", team, ticket, r["team"])
            raise ToolError(FORBIDDEN.format(what=f"test case {ticket}", team=team))   # the owner team is not revealed
        log.info("ALLOW get_test_case team=%s %s", team, ticket)
        return TestCase(ticket=_ticket(r["id"]), team=r["team"], doc_id=r["doc_id"], requirement_ref=r["requirement_ref"],
                        title=r["title"], steps=json.loads(r["steps"]), expected=r["expected"], created_at=r["created_at"])

    if role != "writer":
        return server

    write = mt.ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    @server.tool(annotations=write)
    def create_test_case(
        doc_id: Annotated[str, Field(pattern=DOC_ID, description="Document of the requirement.")],
        requirement_ref: Annotated[str, Field(pattern=REF, description="The passage with the requirement, e.g. remote_work_policy#0000; must belong to doc_id.")],
        title: Annotated[str, Field(min_length=5, max_length=120, description="Short name of the test case.")],
        steps: Annotated[list[Annotated[str, Field(min_length=3, max_length=300)]], Field(min_length=1, max_length=10, description="Actions of the tester, in order.")],
        expected: Annotated[str, Field(min_length=5, max_length=500, description="Expected result.")],
        idempotency_key: Annotated[str, Field(pattern=KEY, description="The same key = the same test case: a repeated call returns the existing one.")],
        run_id: Annotated[Optional[str], Field(None, max_length=80, description="Id of the client's request, kept for the audit.")] = None,
    ) -> CreatedTestCase:
        """Creates a test case of your team in the TMS. Idempotent: a call with an idempotency_key that was used
        before returns the existing test case with created=false and writes nothing."""
        if requirement_ref.split("#")[0] != doc_id:
            raise ToolError(f"validation error: requirement_ref {requirement_ref} does not belong to document {doc_id}")
        tms = Tms(db_path)
        try:
            tc, created = tms.create(doc_id, requirement_ref, title, steps, expected, run_id=run_id,
                                         key=idempotency_key, team=team)
        finally:
            tms.close()
        if tc["team"] != team:
            log.info("DENY create_test_case team=%s key already used by another team", team)
            raise ToolError("CONFLICT (409): this idempotency key is already used; choose another key. Nothing was written.")
        log.info("%s create_test_case team=%s %s %s", "CREATE" if created else "DUPLICATE", team, tc["ticket"], requirement_ref)
        return CreatedTestCase(ticket=tc["ticket"], created=created, team=team, doc_id=tc["doc_id"],
                               requirement_ref=tc["requirement_ref"], title=tc["title"])

    return server


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(name)s %(message)s")  # stdout is the protocol
    team = os.environ.get("TMS_TEAM", "")
    role = os.environ.get("TMS_ROLE", "reader")
    db = os.environ.get("TMS_DB", str(DEFAULT_DB))
    server = make_server(db, team, role)
    log.info("TMS MCP server: team=%s role=%s db=%s", team, role, db)
    server.run("stdio")


if __name__ == "__main__":
    main()
