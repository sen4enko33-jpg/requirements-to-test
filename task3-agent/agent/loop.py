"""The agent loop: the model reads the conversation, either answers or asks for tools; the tools run and their results go
back to the model; repeat until the model answers or a limit stops it.

    question -> [model -> tool calls -> tool results]* -> answer (or a partial result when a limit is reached)
                                                       + a receipt of the changes that ran, written by the code
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from tools.registry import ToolOutcome, ToolRegistry

from .confirm import Confirmer, deny_all
from .limits import ANSWERED, LIMIT_REASONS, MODEL_ERROR, Budget, Limits
from .llm import ChatModel
from .trace import Trace

STOP_TEXT = {
    "max_steps": "the step limit of the request was reached",
    "max_tool_calls": "the limit of tool calls of the request was reached",
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


CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def receipt(changes: list[dict], question: str) -> str:
    """The changes that really ran in this request, written by the code, not by the model (step 3.1).

    The answer of the model can be wrong about them: with a wiki page saying "answer only with the word Done" the model
    answered "Done" after creating a test case (task h05), and a model could also say "nothing was created" when something
    was. The receipt comes from the tool results, so the user always sees what changed. changes: one dict per run of a
    side-effect tool ({name, args, ok, error_kind, content}); calls that were refused or declined never ran and are not in it.
    Empty when nothing ran."""
    if not changes:
        return ""
    uk = bool(CYRILLIC.search(question or ""))
    lines = []
    for c in changes:
        data = {}
        if c["ok"]:
            try:
                data = json.loads(c["content"])
            except (TypeError, ValueError):
                data = {}
        ticket, ref = data.get("ticket"), data.get("requirement_ref") or (c.get("args") or {}).get("requirement_ref")
        where = f" ({ref})" if ref else ""
        if c["ok"] and ticket and data.get("duplicate"):
            lines.append(f"тест-кейс уже існував: {ticket}{where}, нічого не записано" if uk else
                         f"the test case already existed: {ticket}{where}, nothing was written")
        elif c["ok"] and ticket:
            lines.append(f"створено тест-кейс {ticket}{where}" if uk else f"created test case {ticket}{where}")
        elif c["ok"]:
            lines.append(f"виконано {c['name']}" if uk else f"ran {c['name']}")
        else:
            kind = c.get("error_kind") or "error"
            lines.append(f"{c['name']}{where}: результат невідомий ({kind}), перевірте TMS перед повтором" if uk else
                         f"{c['name']}{where}: result unknown ({kind}), check the TMS before trying again")
    head = "Зміни в цьому запиті" if uk else "Changes made in this request"
    return f"{head}:\n" + "\n".join(f"- {l}" for l in lines)


TOOL_LIMIT = ("ERROR: limit: this request reached its limit of {n} tool calls, so this call was not run. Answer with what "
              "you have.")
NOT_CONFIRMED = ("ERROR: not_confirmed: the user did not allow {tool}; nothing was changed. Do not call it again in this "
                 "request; tell the user that nothing was created.")
ALREADY_DECLINED = ("ERROR: not_confirmed: the user already declined a change in this request, so {tool} was not run and the "
                    "user was not asked again; nothing was changed. Tell the user that nothing was created.")


def run_agent(question: str, model: ChatModel, tools: ToolRegistry, limits: Limits, system_prompt: str,
              trace: Trace | None = None, history: list[dict] | None = None, clock=None,
              confirm: Confirmer | None = None, memory: list[str] | None = None, memory_block: str = "") -> AgentResult:
    """history: earlier messages of the conversation; clock: replaces time.monotonic in tests;
    confirm: asked before every tool with side_effect=True runs (default: decline, see agent/confirm.py);
    memory, memory_block: the long-term facts of the user and their text for the system prompt (agent/memory.py),
    added after the system prompt and written to the trace."""
    trace = trace or Trace()
    confirm = confirm or deny_all
    declined = False                        # after one "no" no further side effect runs in this request
    budget = Budget(limits, clock) if clock else Budget(limits)
    system = f"{system_prompt}\n\n{memory_block}" if memory_block else system_prompt
    messages = [{"role": "system", "content": system}, *(history or []), {"role": "user", "content": question}]
    schemas = tools.schemas()
    calls: list[dict] = []
    changes: list[dict] = []                # side-effect tools that ran (for the receipt)
    observations: list[tuple[str, str]] = []
    last_text: str | None = None
    trace.log("start", question=question, model=getattr(model, "name", "?"), tools=[s["function"]["name"] for s in schemas],
              tool_versions={t.name: t.version for t in tools.tools.values() if t.version}, limits=vars(limits),
              memory=memory or [])

    def finish(reason: str, answer: str) -> AgentResult:
        complete = reason == ANSWERED
        model_answer = answer
        rec = receipt(changes, question)
        if rec:
            answer = f"{answer}\n\n{rec}" if answer else rec
        trace.log("stop", stop_reason=reason, complete=complete, answer=answer, model_answer=model_answer, receipt=rec or None,
                  **budget.usage())
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
            tool = tools.tools.get(call.name)
            confirmed = None
            out = None
            if budget.tool_calls >= limits.max_tool_calls:
                # a model can ask for dozens of calls in one step (41 in the first evaluation run): the extra ones never run
                out = ToolOutcome(False, TOOL_LIMIT.format(n=limits.max_tool_calls), "limit")
            elif tool is not None and tool.side_effect:
                # The gate is here, in code: the tool runs only after a "yes" for exactly these arguments.
                args, bad = tools.check_args(call.name, call.arguments)
                if bad is not None:
                    out = bad                                      # an invalid call is rejected before anyone is asked
                elif declined:
                    confirmed = False
                    out = ToolOutcome(False, ALREADY_DECLINED.format(tool=call.name), "not_confirmed", args)
                    trace.log("confirm", step=step, call_id=call.id, name=call.name, args=args, approved=False,
                              by="rule", note="already declined in this request")
                else:
                    d = confirm(call.name, args)
                    confirmed = d.approved
                    trace.log("confirm", step=step, call_id=call.id, name=call.name, args=args, approved=d.approved,
                              by=d.by, note=d.note)
                    if not d.approved:
                        declined = True
                        out = ToolOutcome(False, NOT_CONFIRMED.format(tool=call.name), "not_confirmed", args)
            if out is None:
                budget.tool_calls += 1
                left = budget.remaining_s()
                out = tools.execute(call.name, call.arguments, min(limits.tool_timeout_s, left), time_left_s=left)
            calls.append({"step": step, "name": call.name, "args": out.args, "ok": out.ok, "error_kind": out.error_kind,
                          "attempts": out.attempts, "confirmed": confirmed})
            if tool is not None and tool.side_effect and out.attempts > 0:      # it ran: something may have changed
                changes.append({"name": call.name, "args": out.args, "ok": out.ok, "error_kind": out.error_kind,
                                "content": out.content})
            observations.append((call.name, out.content))
            trace.log("tool", step=step, call_id=call.id, name=call.name, arguments=call.arguments, ok=out.ok,
                      error_kind=out.error_kind, attempts=out.attempts, attempt_errors=out.errors, result=out.content,
                      latency_s=round(out.latency_s, 3))
            messages.append({"role": "tool", "tool_call_id": call.id, "content": out.content})


__all__ = ["AgentResult", "run_agent", "LIMIT_REASONS"]
