"""Runs the task set on the agent and writes the results:  python -m evals.run  (from task3-agent/)

  python -m evals.run                      # every task once
  python -m evals.run --repeat 3           # three runs per task (to see what is stable)
  python -m evals.run --only a01,f04       # some tasks;  --category fault,side_effect  some groups

Every task runs with its own empty TMS (plus the tickets of its `setup`), its own FAULTS, its own confirmations
(`answers`, the rest is "no") and its own limits. The TMS is one file of the run (tms.db, cleared for every task,
deleted at the end), read by the MCP TMS server, which is started once for the run. Output in evals/runs/<date-time>/:
  traces/<task>_r<n>.jsonl   the trace of every run
  results.jsonl              one line per run: passed, failed checks, stop reason, steps, tokens, cost, tools, answer
  summary.md, summary.json   the metrics (pass rate, tool use, actions without permission, steps and cost per task)
Needs OPENROUTER_API_KEY (as main.py); a full run of 30 tasks costs about 0.02 USD."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from agent.confirm import ScriptedConfirmer  # noqa: E402
from agent.limits import LIMIT_REASONS, Limits  # noqa: E402
from agent.llm import make_model  # noqa: E402
from agent.loop import run_agent  # noqa: E402
from agent.trace import Trace  # noqa: E402
from evals.checks import run_checks, tool_names, unconfirmed_side_effects  # noqa: E402
from mcp_server.seed import seed  # noqa: E402
from tools.build import build_registry  # noqa: E402
from tools.corpus import Corpus  # noqa: E402
from tools.mcp_tools import McpTmsStore, mcp_tools, open_server  # noqa: E402
from tools.session import Session  # noqa: E402
from tools.tms import Tms, idempotency_key  # noqa: E402

TASKS = ROOT / "evals" / "tasks.jsonl"
RUNS = ROOT / "evals" / "runs"
TOOL_CHECKS = ("tools_required", "tools_forbidden", "tool_calls_max")


def load_tasks(path: Path = TASKS) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def setup_tms(task: dict, tms: Tms | None = None) -> Tms:
    """An empty TMS with the tickets of the task's setup, keyed like the agent keys them (request + ref); with
    setup.seed the demo rows of another team (mcp_server/seed.py) come first, so the access tasks have something to deny.
    tms: the file of this evaluation run that the MCP server reads (cleared here); None = a new one in memory."""
    if tms is None:
        tms = Tms(":memory:")
    else:
        tms.clear()
    if task.get("setup", {}).get("seed"):
        seed(tms)                     # the rows of another team first (TC-0001, TC-0002 of payments-qa), then ours
    for i, tk in enumerate(task.get("setup", {}).get("tickets", []), 1):
        doc = tk["requirement_ref"].split("#")[0]
        tms.create(doc, tk["requirement_ref"], tk.get("title", f"Existing test case {i}"), tk.get("steps", ["existing step"]),
                       tk.get("expected", "existing expected result"), "setup",
                       idempotency_key("request", tk["requirement_ref"], tk["request"]))
    return tms


def run_task(task: dict, rep: int, cfg: dict, model, corpus: Corpus, system_prompt: str, trace_dir: Path | None,
             sleep=None, tms: Tms | None = None, mcp=None) -> dict:
    """One run of one task -> a result row. A crash of the agent run is recorded as a failed task with the error (the other
    tasks still run); a broken task definition raises (tests/test_checks.py validates tasks.jsonl so it does not happen)."""
    run_id = f"{task['id']}_r{rep}"
    trace = Trace(trace_dir, run_id=run_id) if trace_dir else Trace(run_id=run_id)
    if trace.path and trace.path.exists():
        trace.path.unlink()
    tms = setup_tms(task, tms)
    before = tms.count()
    session = Session(run_id=run_id, request=task["question"])
    limits = Limits.from_config({**cfg["limits"], **task.get("limits", {})})
    confirm = ScriptedConfirmer(*[a == "y" for a in task.get("answers", [])])
    row = {"id": task["id"], "category": task["category"], "rep": rep, "question": task["question"], "faults": task.get("faults")}
    t0 = time.perf_counter()
    try:
        tools = build_registry(cfg, corpus, tms, session, task.get("faults"), sleep=sleep, quiet=True,
                               extra_tools=mcp_tools(mcp, cfg["mcp"]["tms"].get("hidden", ())) if mcp else [],
                               ticket_store=McpTmsStore(mcp))     # no server -> writes are unavailable
        r = run_agent(task["question"], model, tools, limits, system_prompt, trace, confirm=confirm)
    except Exception as e:                                 # a bug of the harness or the agent: recorded, the run goes on
        row.update(passed=False, error=f"{type(e).__name__}: {e}", traceback=traceback.format_exc(),
                   elapsed_s=round(time.perf_counter() - t0, 2), failed=["crash"])
        return row
    events = trace.events
    checks = run_checks(task, r.answer, r.stop_reason, r.usage["steps"], events, before, tms.count())
    failed = [c for c in checks if not c.ok]
    row.update(
        passed=not failed,
        failed=[f"{c.name}" + (f" ({c.detail})" if c.detail else "") for c in failed],
        tool_checks_ok=all(c.ok for c in checks if c.name.startswith(TOOL_CHECKS)) if any(c.name.startswith(TOOL_CHECKS) for c in checks) else None,
        unconfirmed_actions=len(unconfirmed_side_effects(events)),
        tickets_created=tms.count() - before,
        stop_reason=r.stop_reason, steps=r.usage["steps"], tokens_in=r.usage["tokens_in"], tokens_out=r.usage["tokens_out"],
        cost_usd=r.usage["cost_usd"], elapsed_s=r.usage["elapsed_s"], tools=tool_names(events), answer=r.answer,
        trace=_rel(trace.path))
    return row


def _rel(path: Path | None) -> str | None:
    """Path relative to task3-agent when it is inside it (committed runs), else absolute."""
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def summarize(rows: list[dict], meta: dict) -> tuple[dict, str]:
    """Metrics over all runs and a Markdown report."""
    n = len(rows)
    ok_rows = [r for r in rows if "error" not in r]
    by_task = defaultdict(list)
    for r in rows:
        by_task[r["id"]].append(r)
    tool_rows = [r for r in ok_rows if r.get("tool_checks_ok") is not None]
    steps = [r["steps"] for r in ok_rows]
    costs = [r["cost_usd"] for r in ok_rows]
    s = {
        **meta,
        "runs": n, "tasks": len(by_task),
        "pass_rate": round(sum(r["passed"] for r in rows) / n, 3) if n else 0,
        "tasks_passed_every_run": sum(all(x["passed"] for x in v) for v in by_task.values()),
        "tool_use_correct": round(sum(r["tool_checks_ok"] for r in tool_rows) / len(tool_rows), 3) if tool_rows else None,
        "unconfirmed_actions": sum(r.get("unconfirmed_actions", 0) for r in ok_rows),
        "crashes": n - len(ok_rows),
        "steps_mean": round(statistics.mean(steps), 2) if steps else 0, "steps_max": max(steps, default=0),
        "cost_per_task_usd": round(statistics.mean(costs), 6) if costs else 0, "cost_total_usd": round(sum(costs), 5),
        "cost_per_1000_requests_usd": round(statistics.mean(costs) * 1000, 2) if costs else 0,
        "stopped_on_limit": sum(r.get("stop_reason") in LIMIT_REASONS for r in ok_rows),
    }
    cats = defaultdict(list)
    for r in rows:
        cats[r["category"]].append(r["passed"])
    s["pass_rate_by_category"] = {c: f"{sum(v)}/{len(v)}" for c, v in cats.items()}

    reps = meta.get("repeat", 1)
    lines = [f"# Evaluation run {meta['run']}", "",
             f"Model `{meta['model']}`, system prompt `{meta['system_prompt']}`, {s['tasks']} tasks x {reps} run(s) = {n} runs.", "",
             "| metric | value |", "|---|---|",
             f"| runs passed (all checks of the task) | {sum(r['passed'] for r in rows)}/{n} ({s['pass_rate']:.0%}) |",
             f"| tasks passed in every run | {s['tasks_passed_every_run']}/{s['tasks']} |",
             f"| right tools called (runs with tool checks) | {s['tool_use_correct']:.0%} of {len(tool_rows)} |" if tool_rows else "| right tools called | - |",
             f"| actions without permission | {s['unconfirmed_actions']} |",
             f"| stopped on a limit | {s['stopped_on_limit']} |",
             f"| crashes of the harness | {s['crashes']} |",
             f"| steps per task: mean / max | {s['steps_mean']} / {s['steps_max']} |",
             f"| cost per task: mean | ${s['cost_per_task_usd']:.5f} (${s['cost_per_1000_requests_usd']:.2f} per 1000 requests) |",
             f"| cost of the run | ${s['cost_total_usd']:.4f} |", "",
             "| category | passed |", "|---|---|"] + [f"| {c} | {v} |" for c, v in s["pass_rate_by_category"].items()] + [
             "", "| task | category | passed | steps | cost | tools | failed checks |", "|---|---|---|---|---|---|---|"]
    for tid, runs in by_task.items():
        p = sum(r["passed"] for r in runs)
        fails = sorted({f for r in runs for f in r.get("failed", [])})
        tools = ", ".join(sorted({t for r in runs for t in r.get("tools", [])})) or "-"
        mean_steps = statistics.mean(r.get("steps", 0) for r in runs)
        mean_cost = statistics.mean(r.get("cost_usd", 0) for r in runs)
        mark = "" if p in (0, len(runs)) else " (unstable)"
        lines.append(f"| {tid} | {runs[0]['category']} | {p}/{len(runs)}{mark} | {mean_steps:.1f} | ${mean_cost:.5f} | {tools} | "
                     f"{'<br>'.join(f.replace('|', '/') for f in fails) or '-'} |")
    return s, "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--only", help="comma-separated task ids")
    ap.add_argument("--category", help="comma-separated categories")
    ap.add_argument("--out", help="output folder (default evals/runs/<date-time>)")
    a = ap.parse_args()

    load_dotenv(ROOT / ".env"); load_dotenv(ROOT.parent / ".env")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    key = (os.getenv(cfg["model"]["api_key_env"]) or "").strip()
    if key in {"", "your-key-here"}:
        sys.exit(f"no {cfg['model']['api_key_env']} in .env")
    tasks = load_tasks()
    if a.only:
        want = {x.strip() for x in a.only.split(",")}
        tasks = [t for t in tasks if t["id"] in want]
    if a.category:
        want = {x.strip() for x in a.category.split(",")}
        tasks = [t for t in tasks if t["category"] in want]
    if not tasks:
        sys.exit("no tasks selected")

    run_name = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(a.out) if a.out else RUNS / run_name
    (out / "traces").mkdir(parents=True, exist_ok=True)
    system_prompt = (ROOT / "prompts" / f"system_{cfg['system_prompt']}.md").read_text(encoding="utf-8").strip()
    model = make_model(cfg, key)
    corpus = Corpus()
    corpus.warm_up()
    tms = Tms(out / "tms.db")       # one file for the run, cleared for every task; the MCP server reads it
    mcp = open_server(cfg, "tms", db=tms.path)
    meta = {"run": run_name, "mcp_tools": [t.name for t in mcp.tools] if mcp else [], "model": model.name, "system_prompt": cfg["system_prompt"], "repeat": a.repeat,
            "tasks_file": str(TASKS.relative_to(ROOT))}

    rows = []
    with (out / "results.jsonl").open("w", encoding="utf-8") as f:
        for rep in range(1, a.repeat + 1):
            for t in tasks:
                row = run_task(t, rep, cfg, model, corpus, system_prompt, out / "traces", tms=tms, mcp=mcp)
                rows.append(row)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                print(f"{'PASS' if row['passed'] else 'FAIL'} {t['id']} r{rep} {row.get('stop_reason', 'crash')} "
                      f"steps={row.get('steps', '-')} ${row.get('cost_usd', 0):.5f}"
                      + ("" if row["passed"] else f"  {row.get('failed')}"), flush=True)
    if mcp:
        mcp.close()
    tms.close()
    (out / "tms.db").unlink(missing_ok=True)
    summary, md = summarize(rows, meta)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "summary.md").write_text(md, encoding="utf-8")
    print(f"\n{summary['pass_rate']:.0%} of runs passed, {summary['unconfirmed_actions']} actions without permission, "
          f"${summary['cost_total_usd']:.4f} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
