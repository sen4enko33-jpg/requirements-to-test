"""Tools of the agent: a description, a schema of the arguments and of the answer (Pydantic) and a function.

`execute` never raises. Every problem comes back as a text that starts with "ERROR: <kind>:", which goes to the model as
the tool result, so the model can fix the call or tell the user, and the agent keeps running:

  unknown_tool, bad_json, invalid_args  the call is wrong: the model can fix it (never retried)
  timeout, rate_limited, unavailable    the service is slow or down (429 / 503): retried with backoff, but only for safe
                                        (read-only) tools; after the last attempt the model is told the service is down
  bad_output                            the tool answered in another format than its output schema (an API that renamed
                                        or dropped a field): not retried, the field is named in the error and the trace
  forbidden, not_found                  a decision of the service (403 / 404, e.g. the MCP TMS): not retried, the
                                        message of the service goes to the model as it is
  not_requested                         a change the user's message did not ask for (tools/ticket_tool.py): not run,
                                        nobody is asked to confirm it
  tool_error                            any other exception (not retried)
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ValidationError


class ToolInputError(ValueError):
    """Raised by a tool when the arguments are valid by the schema but wrong for the data (an unknown doc_id or ref).
    The model gets it as ERROR: invalid_args, like a schema error, so it can fix the call."""


class ToolUnavailable(RuntimeError):
    """The service behind a tool answered 429 (rate limit) or 5xx, or its own client timed out (status None)."""

    def __init__(self, status: int | None, message: str = "", retry_after_s: float | None = None):
        super().__init__(message or (f"HTTP {status}" if status else "timeout"))
        self.status, self.retry_after_s = status, retry_after_s

    @property
    def kind(self) -> str:
        return "timeout" if self.status is None else "rate_limited" if self.status == 429 else "unavailable"


class ToolRefused(RuntimeError):
    """The service answered, and the answer is a refusal that a retry cannot change: 403 forbidden, 404 not found."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


RETRYABLE_KINDS = ("timeout", "rate_limited", "unavailable")


@dataclass
class RetryPolicy:
    max_attempts: int = 3           # attempts of a safe tool, the first one included
    backoff_s: float = 0.5          # pause before the 2nd attempt; doubled for every next one
    backoff_max_s: float = 4.0

    @classmethod
    def from_config(cls, cfg: dict | None) -> "RetryPolicy":
        return cls(**{k: v for k, v in (cfg or {}).items() if k in ("max_attempts", "backoff_s", "backoff_max_s")})

    def pause(self, attempt: int, retry_after_s: float | None = None) -> float:
        """Pause after the failed attempt number `attempt` (1-based). A Retry-After of the service wins when it is longer."""
        p = min(self.backoff_max_s, self.backoff_s * 2 ** (attempt - 1))
        return max(p, retry_after_s or 0.0)


@dataclass
class Tool:
    name: str
    description: str                       # when to call it, when not, what it returns
    args_model: type[BaseModel]            # schema of the arguments (sent to the model as JSON Schema)
    fn: Callable[[BaseModel], Any]         # gets the validated arguments, returns something JSON-serialisable
    safe: bool = True                      # read-only: may be repeated after a timeout / 429 / 503
    side_effect: bool = False              # changes something outside the conversation (needs a human confirmation)
    version: str = ""                      # version of the description (prompts/tools/<name>.yaml), written to the trace
    output_model: type[BaseModel] | None = None   # schema of the answer; checked before the answer reaches the model
    precheck: Callable[[BaseModel], None] | None = None   # checks before anything (raises ToolInputError or ToolRefused)
                                                          # runs - and before a person is asked to confirm the call

    def schema(self) -> dict:
        params = self.args_model.model_json_schema()
        params.pop("title", None)
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": params}}


@dataclass
class ToolOutcome:
    ok: bool
    content: str                           # what the model gets as the tool result
    error_kind: str | None = None          # see the module docstring
    args: dict | None = None               # the validated arguments (None when they were invalid)
    latency_s: float = 0.0
    attempts: int = 0                      # how many times the tool ran (0 when the call was rejected before running)
    errors: list[str] = field(default_factory=list)   # the error of every failed attempt, for the trace


def _short_validation(e: ValidationError, what: str = "arguments", limit: int = 3) -> str:
    errs = e.errors()
    text = "; ".join(f"{'.'.join(map(str, err['loc'])) or what}: {err['msg']}" for err in errs[:limit])
    return text + (f"; and {len(errs) - limit} more" if len(errs) > limit else "")


UNAVAILABLE_HINT = ("Tell the user that this service is unavailable right now and that you cannot answer from the documents; "
                    "do not answer from memory and do not say the documents do not cover the question.")


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None, retry: RetryPolicy | None = None, sleep=time.sleep):
        """sleep: replaced in tests, so the backoff pauses are recorded instead of waited."""
        self.tools: dict[str, Tool] = {}
        self.retry = retry or RetryPolicy()
        self.sleep = sleep
        for t in tools or []:
            self.add(t)

    def add(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"tool {tool.name!r} is registered twice")
        self.tools[tool.name] = tool

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self.tools.values()]

    def _run_once(self, tool: Tool, args: BaseModel, timeout_s: float):
        """-> (kind, message, retry_after) on failure or (None, content, None) on success."""
        # The tool runs in a worker thread so that a slow tool cannot block the agent past the timeout. Python cannot
        # kill the thread: a timed-out tool may still finish in the background, its result is ignored.
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            result = pool.submit(tool.fn, args).result(timeout=timeout_s)
        except ToolInputError as e:
            return "invalid_args", str(e), None
        except ToolUnavailable as e:
            return e.kind, f"{tool.name}: {e}", e.retry_after_s
        except ToolRefused as e:
            return e.kind, str(e), None
        except FutureTimeout:
            return "timeout", f"{tool.name} did not answer within {timeout_s:.1f} s", None
        except Exception as e:
            return "tool_error", f"{type(e).__name__}: {e}", None
        finally:
            pool.shutdown(wait=False)
        if tool.output_model is not None and not isinstance(result, str):
            try:
                tool.output_model.model_validate(result)
            except ValidationError as e:
                return "bad_output", (f"{tool.name} answered in an unexpected format ({_short_validation(e, 'answer')}). "
                                      "This is a failure of the service, not a missing answer: tell the user that the "
                                      "service returned invalid data and that you cannot answer now. Do not say the "
                                      "documents do not cover the question."), None
        return None, result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str), None

    def check_args(self, name: str, raw_args: str) -> tuple[dict | None, ToolOutcome | None]:
        """Validate a call without running it -> (arguments, None) or (None, the error outcome). The agent loop uses it to
        show a person exactly what a side-effect tool will do before asking for the confirmation."""
        tool = self.tools.get(name)
        if tool is None:
            return None, ToolOutcome(False, f"ERROR: unknown_tool: no tool named {name!r}; available: {', '.join(self.tools)}",
                                     "unknown_tool")
        try:
            data = json.loads(raw_args or "{}")
        except json.JSONDecodeError as e:
            return None, ToolOutcome(False, f"ERROR: bad_json: arguments are not valid JSON ({e.msg})", "bad_json")
        try:
            args = tool.args_model.model_validate(data)
        except ValidationError as e:
            return None, ToolOutcome(False, f"ERROR: invalid_args: {_short_validation(e)}", "invalid_args")
        if tool.precheck is not None:
            try:
                tool.precheck(args)
            except ToolInputError as e:
                return None, ToolOutcome(False, f"ERROR: invalid_args: {e}", "invalid_args", args.model_dump())
            except ToolRefused as e:
                return None, ToolOutcome(False, f"ERROR: {e.kind}: {e}", e.kind, args.model_dump())
        return args.model_dump(), None

    def execute(self, name: str, raw_args: str, timeout_s: float, time_left_s: float | None = None) -> ToolOutcome:
        """timeout_s: limit of one attempt; time_left_s: time left for the whole request (retries and pauses stop
        when it runs out; None = only timeout_s counts)."""
        start = time.perf_counter()
        deadline = start + (time_left_s if time_left_s is not None else timeout_s * self.retry.max_attempts + 60)

        def fail(kind, msg, args=None, attempts=0, errors=None):
            return ToolOutcome(False, f"ERROR: {kind}: {msg}", kind, args, time.perf_counter() - start, attempts, errors or [])

        tool = self.tools.get(name)
        if tool is None:
            return fail("unknown_tool", f"no tool named {name!r}; available: {', '.join(self.tools)}")
        try:
            data = json.loads(raw_args or "{}")
        except json.JSONDecodeError as e:
            return fail("bad_json", f"arguments are not valid JSON ({e.msg})")
        try:
            args = tool.args_model.model_validate(data)
        except ValidationError as e:
            return fail("invalid_args", _short_validation(e))
        args_dict = args.model_dump()
        if tool.precheck is not None:
            try:
                tool.precheck(args)
            except ToolInputError as e:
                return fail("invalid_args", str(e), args_dict)
            except ToolRefused as e:
                return fail(e.kind, str(e), args_dict)
        if timeout_s <= 0:
            return fail("timeout", "no time left for this request", args_dict)

        errors: list[str] = []
        attempts = 0
        max_attempts = self.retry.max_attempts if tool.safe else 1
        while True:
            left = deadline - time.perf_counter()
            if left <= 0:
                return fail("timeout", "no time left for this request" + (f" after {attempts} attempt(s)" if attempts else ""),
                            args_dict, attempts, errors)
            attempts += 1
            kind, msg, retry_after = self._run_once(tool, args, min(timeout_s, left))
            if kind is None:
                return ToolOutcome(True, msg, None, args_dict, time.perf_counter() - start, attempts, errors)
            errors.append(f"{kind}: {msg}")
            if kind not in RETRYABLE_KINDS:
                return fail(kind, msg, args_dict, attempts, errors)
            pause = self.retry.pause(attempts, retry_after)
            if attempts >= max_attempts or time.perf_counter() + pause >= deadline:
                why = (f"after {attempts} attempt(s)" if tool.safe else "not retried: the tool changes data")
                return fail(kind, f"{msg} ({why}). {UNAVAILABLE_HINT}", args_dict, attempts, errors)
            self.sleep(pause)
