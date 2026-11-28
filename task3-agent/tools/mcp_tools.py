"""The agent as an MCP client (step 2.2): the tools of an MCP server become ordinary tools of the agent's registry.

    with McpConnection(stdio_params(cfg["mcp"]["tracker"], db=...)) as conn:
        tools = mcp_tools(conn)          # -> [Tool, ...] for ToolRegistry

What comes from the server and what stays in the agent:
  - from the server (tools/list): the names, the descriptions, the argument schema (inputSchema), the answer schema
    (outputSchema) and the annotations; readOnlyHint=True -> safe (may be retried), otherwise side_effect=True (a person
    must confirm it, agent/loop.py). The server decides what a tool is; the agent does not keep a copy that can go stale.
  - in the agent, exactly as for the local tools (tools/registry.py): the arguments are checked against the server's schema
    BEFORE the call, the timeout of one call, the retries of safe tools after timeout / 503, FAULTS, the check of the answer
    against its schema, the limits and the trace.

Errors of the server -> "ERROR: <kind>:" for the model (tools/registry.py):
  FORBIDDEN (403)      -> forbidden    a permission decision of the server; never retried
  NOT_FOUND (404)      -> not_found    the object does not exist; never retried
  CONFLICT (409)       -> conflict     the idempotency key of a write belongs to another team; never retried
  UNAVAILABLE (503)    -> unavailable  retried for safe tools, as a 503 of any service
  validation error     -> invalid_args the server rejected the arguments (normally caught before, by the schema here)
  the server process died, the call did not answer in time -> unavailable / timeout
  any other error      -> tool_error

The agent loop is synchronous and the mcp library is asynchronous: McpConnection runs one event loop in its own thread for
the whole request and keeps the session open there; call_tool() hands a coroutine to that loop and waits for it."""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import sys
import threading
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any, TextIO

import jsonschema
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, ConfigDict, model_validator
from pydantic_core import PydanticCustomError

from .registry import Tool, ToolInputError, ToolRefused, ToolUnavailable

ROOT = Path(__file__).resolve().parents[1]
PREFIX = re.compile(r"^Error executing tool [\w-]+: ")     # added by the mcp library in front of the server's message
KINDS = [("FORBIDDEN (403)", "forbidden"), ("NOT_FOUND (404)", "not_found"), ("CONFLICT (409)", "conflict")]


class McpError(RuntimeError):
    """The connection to an MCP server could not be opened."""


def stdio_params(cfg: dict, db: str | Path | None = None) -> StdioServerParameters:
    """The command that starts a server of this repository (config.yaml, section mcp) with the agent's own interpreter.
    db: the tracker file the agent uses, so that the server reads the same rows."""
    env = {**os.environ, **{k: str(v) for k, v in (cfg.get("env") or {}).items()}}   # PATH, HOME, ... + the server's own
    if db is not None:
        env["TRACKER_DB"] = str(db)
    return StdioServerParameters(command=sys.executable, args=["-m", cfg["module"]], env=env, cwd=str(ROOT))


class McpConnection:
    """One MCP session for the whole agent request, usable from synchronous code (and from the registry's worker threads).

    server: StdioServerParameters (a subprocess, as in main.py) or an MCPServer instance (in-process, in tests)."""

    def __init__(self, server: Any, start_timeout_s: float = 30.0, call_timeout_s: float = 15.0,
                 errlog: TextIO | None = None, own_errlog: bool = False):
        self.server = server
        self.start_timeout_s, self.call_timeout_s = start_timeout_s, call_timeout_s
        self.errlog = errlog                  # where the subprocess writes its log (stderr of the server); None = ours
        self.own_errlog = own_errlog          # close errlog together with the connection
        self.loop: asyncio.AbstractEventLoop | None = None
        self.client: Client | None = None
        self.tools: list = []
        self.name = self.version = ""
        self.instructions: str | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stop: asyncio.Event | None = None
        self._error: BaseException | None = None
        self.closed = False                   # True once the session ended (closed by us or the server went away)

    # --- life cycle
    def __enter__(self) -> "McpConnection":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> "McpConnection":
        self._thread = threading.Thread(target=self._run, name="mcp-client", daemon=True)
        self._thread.start()
        if not self._ready.wait(self.start_timeout_s):
            self.close()
            raise McpError(f"the MCP server did not start within {self.start_timeout_s:.0f} s")
        if self._error is not None:
            raise McpError(f"the MCP server could not be started: {_describe(self._error)}") from self._error
        return self

    def _run(self) -> None:
        try:
            asyncio.run(self._session())
        except BaseException as e:            # noqa: BLE001 - reported to open() or seen by call_tool as a closed session
            self._error = self._error or e
        finally:
            self.closed = True
            self._ready.set()

    async def _session(self) -> None:
        self.loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        target = self.server
        if isinstance(target, StdioServerParameters) and self.errlog is not None:
            target = stdio_client(target, errlog=self.errlog)
        async with Client(target) as client:
            self.client = client
            self.tools = (await client.list_tools()).tools
            info = client.server_info
            self.name, self.version = (info.name, info.version) if info else ("mcp", "")
            self.instructions = client.instructions
            self._ready.set()
            await self._stop.wait()

    def close(self) -> None:
        if self.loop is not None and self._stop is not None and not self.closed:
            try:
                self.loop.call_soon_threadsafe(self._stop.set)
            except RuntimeError:              # the loop has already ended
                pass
        if self._thread is not None:
            self._thread.join(timeout=10)
        self.closed = True
        if self.own_errlog and self.errlog is not None and not self.errlog.closed:
            self.errlog.close()

    # --- calls
    def call_tool(self, name: str, arguments: dict, timeout_s: float | None = None):
        """-> CallToolResult. Raises ToolUnavailable when the session is gone or the server does not answer in time."""
        if self.closed or self.client is None or self.loop is None:
            raise ToolUnavailable(503, f"the MCP server {self.name or ''} is not running".replace("  ", " "))
        timeout = min(timeout_s or self.call_timeout_s, self.call_timeout_s)
        fut = asyncio.run_coroutine_threadsafe(self.client.call_tool(name, arguments, read_timeout_seconds=timeout),
                                               self.loop)
        try:
            return fut.result(timeout + 1.0)  # the read timeout of the library fires first; this one is the safety net
        except FutureTimeout:
            fut.cancel()
            raise ToolUnavailable(None, f"MCP server {self.name}: {name} did not answer within {timeout:.1f} s")
        except (TimeoutError, asyncio.TimeoutError):
            raise ToolUnavailable(None, f"MCP server {self.name}: {name} did not answer within {timeout:.1f} s")
        except Exception as e:                # the subprocess died, the stream broke, ...
            if self.closed:
                raise ToolUnavailable(503, f"MCP server {self.name} stopped: {_describe(e)}") from e
            msg = _describe(e)
            if "timed out" in msg.lower() or "timeout" in msg.lower():
                raise ToolUnavailable(None, f"MCP server {self.name}: {name} did not answer within {timeout:.1f} s") from e
            raise ToolUnavailable(503, f"MCP server {self.name}: {msg}") from e


def _describe(e: BaseException) -> str:
    """A short text of an exception; exception groups of anyio are unwrapped to their first leaf."""
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__


def _text(result) -> str:
    return "".join(getattr(c, "text", "") for c in result.content).strip()


def _schema_model(tool_name: str, schema: dict, what: str) -> type[BaseModel]:
    """A Pydantic class that validates with a JSON Schema from the server, so the registry can use it as it uses the
    models of the local tools: model_validate() rejects what the schema rejects, model_json_schema() is the server's schema."""
    checker = jsonschema.Draft202012Validator(schema)
    published = {k: v for k, v in schema.items() if k != "title"}

    class FromServer(BaseModel):
        model_config = ConfigDict(extra="allow")

        @model_validator(mode="before")
        @classmethod
        def _check(cls, data):
            if not isinstance(data, dict):
                raise PydanticCustomError("schema", f"{what} must be a JSON object")
            errors = sorted(checker.iter_errors(data), key=lambda e: list(e.absolute_path))
            if errors:
                # becomes a ValidationError of pydantic: the registry reports it as invalid_args / bad_output
                raise PydanticCustomError("schema", "; ".join(
                    f"{'.'.join(map(str, e.absolute_path)) or what}: {e.message}" for e in errors[:3]))
            return data

        @classmethod
        def model_json_schema(cls, *a, **kw) -> dict:     # what the model sees: exactly the server's schema
            return json.loads(json.dumps(published))

    FromServer.__name__ = FromServer.__qualname__ = f"{tool_name}_{what}"
    return FromServer


def call(conn: McpConnection, name: str, arguments: dict):
    """tools/call -> the answer (structured content, or the text parsed as JSON, or the text). An error of the server is
    raised as the exception the registry turns into "ERROR: <kind>:" (see the module docstring)."""
    result = conn.call_tool(name, arguments)
    if result.is_error:
        msg = PREFIX.sub("", _text(result)) or "the server reported an error without a message"
        for marker, kind in KINDS:
            if marker in msg:
                raise ToolRefused(kind, msg)
        if "UNAVAILABLE (503)" in msg:
            raise ToolUnavailable(503, msg)
        if "validation error" in msg.lower():
            raise ToolInputError(msg)
        raise RuntimeError(msg)
    if result.structured_content is not None:
        return result.structured_content
    text = _text(result)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def make_mcp_tool(conn: McpConnection, spec) -> Tool:
    """One tool of the server as a Tool of the agent."""
    ann = spec.annotations
    read_only = bool(ann and ann.read_only_hint)
    args_model = _schema_model(spec.name, spec.input_schema or {"type": "object"}, "arguments")
    output_model = _schema_model(spec.name, spec.output_schema, "answer") if spec.output_schema else None

    def fn(args: BaseModel):
        return call(conn, spec.name, {k: v for k, v in args.model_dump().items() if v is not None})

    return Tool(spec.name, inspect.cleandoc(spec.description or spec.name), args_model, fn,
                safe=read_only, side_effect=not read_only, version=f"mcp:{conn.name}@{conn.version or '?'}",
                output_model=output_model)


def mcp_tools(conn: McpConnection, hidden: tuple[str, ...] | list[str] = ()) -> list[Tool]:
    """The server's tools for the model. hidden: tools the model must not call directly (config.yaml, mcp.<server>.hidden):
    create_test_case is reached only through create_test_ticket, which first checks the requirement against what the agent
    read and asks a person (tools/ticket_tool.py, agent/loop.py)."""
    return [make_mcp_tool(conn, spec) for spec in conn.tools if spec.name not in hidden]


class McpTrackerStore:
    """Where create_test_ticket writes (step 2.3): the tracker MCP server, through its tool create_test_case. It has the
    signature of Tracker.create, so the ticket tool does not care whether it writes to a local file (tests) or to the server.
    conn None (the server did not start): every write is unavailable - the agent never writes past the server."""

    TOOL = "create_test_case"

    def __init__(self, conn: McpConnection | None):
        self.conn = conn

    def create(self, doc_id: str, requirement_ref: str, title: str, steps: list[str], expected: str,
               run_id: str | None = None, key: str | None = None) -> tuple[dict, bool]:
        if self.conn is None or self.conn.closed:
            raise ToolUnavailable(503, "the tracker MCP server is not running; no test case can be created")
        if self.TOOL not in {t.name for t in self.conn.tools}:
            raise ToolRefused("forbidden", f"FORBIDDEN (403): the tracker MCP server offers no {self.TOOL} to this "
                                           "connection (it is connected as a reader); nothing was created")
        if not key:
            raise ValueError("an idempotency key is required for a write through the tracker server")
        args = {"doc_id": doc_id, "requirement_ref": requirement_ref, "title": title, "steps": steps,
                "expected": expected, "idempotency_key": key}
        if run_id:
            args["run_id"] = run_id[:80]
        tc = call(self.conn, self.TOOL, args)
        return tc, bool(tc["created"])


def open_server(cfg: dict, name: str, db: str | Path | None = None, quiet: bool = False) -> McpConnection | None:
    """Start the MCP server `name` of config.yaml (section mcp) for one run -> the open connection, or None when it does not
    start: the agent then works without its tools (and says so on stderr) instead of not working at all."""
    sc = (cfg.get("mcp") or {}).get(name)
    if not sc:
        return None
    log_path = ROOT / sc["log"] if sc.get("log") else None
    errlog = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        errlog = log_path.open("a", encoding="utf-8")
    conn = McpConnection(stdio_params(sc, db), sc.get("start_timeout_s", 30), sc.get("call_timeout_s", 15), errlog,
                         own_errlog=errlog is not None)
    try:
        conn.open()
    except McpError as e:
        if not quiet:
            print(f"[mcp {name}: {e}; running without its tools" + (f", see {log_path}" if log_path else "") + "]",
                  file=sys.stderr)
        return None
    if not quiet:
        print(f"[mcp {name}: {conn.name} {conn.version}, tools {[t.name for t in conn.tools]}]", file=sys.stderr)
    return conn
