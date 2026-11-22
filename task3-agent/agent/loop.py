"""The agent loop: the model reads the conversation, either answers or asks for tools; the tools run and their results go
back to the model; repeat until the model answers or a limit stops it.

    question -> [model -> tool calls -> tool results]* -> answer (or a partial result when a limit is reached)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tools.registry import ToolRegistry

from .limits import ANSWERED, LIMIT_REASONS, MODEL_ERROR, Budget, Limits
from .llm import ChatModel
from .trace import Trace

STOP_TEXT = {
    "max_steps": "the step limit of the request was reached",
    "budget_tokens": "the token budget of the request was used up",
    "budget_cost": "the cost budget of the request was used up",
    "timeout": "the time limit of the request was reached",
    "model_error": "the model service did not answer",
}
PARTIAL_CHARS = 300      # how much of every tool result goes into a partial result


@dataclass
class AgentResult:
    answer: str
    stop_reason: str                       # see agent/limits.py
    complete: bool                         # False when a limit or an error stopped the agent (the answer is partial)
    usage: dict                            # steps, tokens, cost, time
    tool_calls: list[dict] = field(default_factory=list)   # [{step, name, args, ok, error_kind}]
    trace_path: str | None = None
    run_id: str = ""


def _partial(reason: str, last_text: str | None, observations: list[tuple[str, str]]) -> str:
    """What the user gets when the agent is stopped: why, and what it had collected so far (no extra model call, which
    would spend budget that is already used up)."""
    lines = [f"Stopped before a full answer: {STOP_TEXT.get(reason, reason)}."]
    if last_text:
        lines.append(f"Last note of the agent: {last_text.strip()}")
    ok = [(n, c) for n, c in observations if not c.startswith("ERROR:")]
    if ok:
        lines.append("Collected so far:")
        lines += [f"- {n}: {c[:PARTIAL_CHARS]}{'...' if len(c) > PARTIAL_CHARS else ''}" for n, c in ok]
    else:
        lines.append("Nothing useful was collected.")
    return "\n".join(lines)


def run_agent(question: str, model: ChatModel, tools: ToolRegistry, limits: Limits, system_prompt: str,
              trace: Trace | None = None, history: list[dict] | None = None, clock=None) -> AgentResult:
    """history: earlier messages of the conversation (memory comes in a later step); clock: replaces time.monotonic in tests."""
    trace = trace or Trace()
    budget = Budget(limits, clock) if clock else Budget(limits)
    messages = [{"role": "system", "content": system_prompt}, *(history or []), {"role": "user", "content": question}]
    schemas = tools.schemas()
    calls: list[dict] = []
    observations: list[tuple[str, str]] = []
    last_text: str | None = None
    trace.log("start", question=question, model=getattr(model, "name", "?"), tools=[s["function"]["name"] for s in schemas],
              limits=vars(limits))

    def finish(reason: str, answer: str) -> AgentResult:
        complete = reason == ANSWERED
        trace.log("stop", stop_reason=reason, complete=complete, answer=answer, **budget.usage())
        return AgentResult(answer, reason, complete, budget.usage(), calls,
                           str(trace.path) if trace.path else None, trace.run_id)

    while True:
        reason = budget.exceeded()
        if reason:
            return finish(reason, _partial(reason, last_text, observations))
        step = budget.steps + 1
        res = model.chat(messages, schemas, timeout_s=budget.remaining_s())
        budget.add_step(res.tokens_in, res.tokens_out, res.cost_usd)
        trace.log("model", step=step, content=res.content,
                  tool_calls=[{"id": c.id, "name": c.name, "arguments": c.arguments} for c in res.tool_calls],
                  tokens_in=res.tokens_in, tokens_out=res.tokens_out, cost_usd=res.cost_usd, latency_s=round(res.latency_s, 3),
                  attempts=res.attempts, finish_reason=res.finish_reason, error=res.error)
        if res.error:
            return finish(MODEL_ERROR, _partial(MODEL_ERROR, last_text, observations))
        if not res.tool_calls:
            return finish(ANSWERED, (res.content or "").strip())
        last_text = res.content or last_text
        messages.append(res.assistant_message())
        # Every tool call of the step gets a result (the API rejects a conversation with an unanswered call), even when the
        # request runs out of time in the middle: the remaining calls then get a timeout error without running.
        for call in res.tool_calls:
            out = tools.execute(call.name, call.arguments, min(limits.tool_timeout_s, budget.remaining_s()))
            calls.append({"step": step, "name": call.name, "args": out.args, "ok": out.ok, "error_kind": out.error_kind})
            observations.append((call.name, out.content))
            trace.log("tool", step=step, call_id=call.id, name=call.name, arguments=call.arguments, ok=out.ok,
                      error_kind=out.error_kind, result=out.content, latency_s=round(out.latency_s, 3))
            messages.append({"role": "tool", "tool_call_id": call.id, "content": out.content})


__all__ = ["AgentResult", "run_agent", "LIMIT_REASONS"]
