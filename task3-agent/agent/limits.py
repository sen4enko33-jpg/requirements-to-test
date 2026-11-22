"""Limits of one request: steps (model calls), tokens, cost and wall time. They stop an agent that would otherwise loop
(for example, searching again and again for an answer that does not exist) or spend too much."""
from __future__ import annotations

import time
from dataclasses import dataclass, fields

# Why the agent stopped (written to the trace and returned with the answer).
ANSWERED = "answered"          # the model gave a final answer
MAX_STEPS = "max_steps"        # the number of model calls reached limits.max_steps
MAX_TOOL_CALLS = "max_tool_calls"   # the number of tool calls reached limits.max_tool_calls (one step can ask for dozens)
BUDGET_TOKENS = "budget_tokens"
BUDGET_COST = "budget_cost"
TIMEOUT = "timeout"            # the request ran longer than limits.request_timeout_s
MODEL_ERROR = "model_error"    # the model API failed after its retries
LIMIT_REASONS = (MAX_STEPS, MAX_TOOL_CALLS, BUDGET_TOKENS, BUDGET_COST, TIMEOUT)


@dataclass
class Limits:
    max_steps: int = 5
    max_tool_calls: int = 12
    max_tokens_total: int = 40000
    max_cost_usd: float = 0.02
    request_timeout_s: float = 120.0
    tool_timeout_s: float = 20.0

    @classmethod
    def from_config(cls, cfg: dict) -> "Limits":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (cfg or {}).items() if k in known})


class Budget:
    """What one request has used so far. `clock` can be replaced in tests."""

    def __init__(self, limits: Limits, clock=time.monotonic):
        self.limits, self.clock = limits, clock
        self.start = clock()
        self.steps = 0
        self.tool_calls = 0
        self.tokens_in = self.tokens_out = 0
        self.cost_usd = 0.0

    def add_step(self, tokens_in: int, tokens_out: int, cost_usd: float) -> None:
        self.steps += 1
        self.tokens_in += tokens_in or 0
        self.tokens_out += tokens_out or 0
        self.cost_usd += cost_usd or 0.0

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    def elapsed_s(self) -> float:
        return self.clock() - self.start

    def remaining_s(self) -> float:
        return max(0.0, self.limits.request_timeout_s - self.elapsed_s())

    def exceeded(self) -> str | None:
        """The first limit that is used up, or None. Checked before every model call: a call is made only when there is
        budget left, so one call can still go above the token or cost limit (by at most one call)."""
        lim = self.limits
        if self.elapsed_s() >= lim.request_timeout_s:
            return TIMEOUT
        if self.steps >= lim.max_steps:
            return MAX_STEPS
        if self.tool_calls >= lim.max_tool_calls:
            return MAX_TOOL_CALLS
        if self.tokens >= lim.max_tokens_total:
            return BUDGET_TOKENS
        if self.cost_usd >= lim.max_cost_usd:
            return BUDGET_COST
        return None

    def usage(self) -> dict:
        return {"steps": self.steps, "tool_calls": self.tool_calls, "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
                "cost_usd": round(self.cost_usd, 6), "elapsed_s": round(self.elapsed_s(), 3)}
