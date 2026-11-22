"""Tools of the agent: a description, a schema of the arguments (Pydantic) and a function.

`execute` never raises. Unknown tool, broken JSON, invalid arguments, an exception or a timeout of the tool come back as a
text that starts with "ERROR: <kind>:", which goes to the model as the tool result, so the model can fix the call
(or tell the user) and the agent keeps running."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError


class ToolInputError(ValueError):
    """Raised by a tool when the arguments are valid by the schema but wrong for the data (an unknown doc_id or ref).
    The model gets it as ERROR: invalid_args, like a schema error, so it can fix the call."""


@dataclass
class Tool:
    name: str
    description: str                       # when to call it, when not, what it returns
    args_model: type[BaseModel]            # schema of the arguments (sent to the model as JSON Schema)
    fn: Callable[[BaseModel], Any]         # gets the validated arguments, returns something JSON-serialisable
    safe: bool = True                      # read-only: may be repeated (used by retries in a later sub-step)
    side_effect: bool = False              # changes something outside the conversation (needs a human confirmation)
    version: str = ""                      # version of the description (prompts/tools/<name>.yaml), written to the trace

    def schema(self) -> dict:
        params = self.args_model.model_json_schema()
        params.pop("title", None)
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": params}}


@dataclass
class ToolOutcome:
    ok: bool
    content: str                           # what the model gets as the tool result
    error_kind: str | None = None          # unknown_tool | bad_json | invalid_args | timeout | tool_error
    args: dict | None = None               # the validated arguments (None when they were invalid)
    latency_s: float = 0.0


def _error(kind: str, msg: str, start: float, args: dict | None = None) -> ToolOutcome:
    return ToolOutcome(False, f"ERROR: {kind}: {msg}", kind, args, time.perf_counter() - start)


def _short_validation(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, err['loc'])) or 'arguments'}: {err['msg']}" for err in e.errors())


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None):
        self.tools: dict[str, Tool] = {}
        for t in tools or []:
            self.add(t)

    def add(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"tool {tool.name!r} is registered twice")
        self.tools[tool.name] = tool

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self.tools.values()]

    def execute(self, name: str, raw_args: str, timeout_s: float) -> ToolOutcome:
        start = time.perf_counter()
        tool = self.tools.get(name)
        if tool is None:
            return _error("unknown_tool", f"no tool named {name!r}; available: {', '.join(self.tools)}", start)
        try:
            data = json.loads(raw_args or "{}")
        except json.JSONDecodeError as e:
            return _error("bad_json", f"arguments are not valid JSON ({e.msg})", start)
        try:
            args = tool.args_model.model_validate(data)
        except ValidationError as e:
            return _error("invalid_args", _short_validation(e), start)
        args_dict = args.model_dump()
        if timeout_s <= 0:
            return _error("timeout", "no time left for this request", start, args_dict)
        # The tool runs in a worker thread so that a slow tool cannot block the agent past the timeout. Python cannot
        # kill the thread: a timed-out tool may still finish in the background, its result is ignored.
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            result = pool.submit(tool.fn, args).result(timeout=timeout_s)
        except ToolInputError as e:
            return _error("invalid_args", str(e), start, args_dict)
        except FutureTimeout:
            return _error("timeout", f"the tool did not answer within {timeout_s:.0f} s", start, args_dict)
        except Exception as e:
            return _error("tool_error", f"{type(e).__name__}: {e}", start, args_dict)
        finally:
            pool.shutdown(wait=False)
        content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        return ToolOutcome(True, content, None, args_dict, time.perf_counter() - start)
