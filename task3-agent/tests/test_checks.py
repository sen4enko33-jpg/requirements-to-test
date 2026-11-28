"""Checks of the evaluation checks themselves on hand-made traces (no network): python tests/test_checks.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.checks import cited_refs, run_checks, seen_refs, unconfirmed_side_effects

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


def tool(name, result, ok=True, call_id="c0", attempts=1):
    return {"event": "tool", "name": name, "ok": ok, "call_id": call_id, "attempts": attempts,
            "result": result if isinstance(result, str) else json.dumps(result)}


def confirm(call_id, approved):
    return {"event": "confirm", "call_id": call_id, "approved": approved}


SEARCH = tool("search_corpus", {"results": [{"ref": "remote_work_policy#0000"}, {"ref": "remote_work_policy_2023#0000"}]})
ANSWER = "До двох днів на тиждень [remote_work_policy#0000]. У 2023 було три [remote_work_policy_2023#0000]."


def results(expect, answer=ANSWER, events=(SEARCH,), stop="answered", steps=2, before=0, after=0):
    cs = run_checks({"id": "t", "expect": expect}, answer, stop, steps, list(events), before, after)
    return {c.name: c.ok for c in cs}, cs


def passed(expect, **kw):
    r, _ = results(expect, **kw)
    return all(r.values())


# --- helpers
check("cited_refs: one per bracket and joined brackets",
      cited_refs("a [x#0001][y_z#0002] b [w#0003]") == ["x#0001", "y_z#0002", "w#0003"])
check("cited_refs: plain text in brackets is not a ref", cited_refs("[TC-0001] [note]") == [])
check("seen_refs: refs of search results and passages",
      seen_refs([SEARCH, tool("get_passage", {"passages": [{"ref": "a#0001"}]})]) == {"remote_work_policy#0000", "remote_work_policy_2023#0000", "a#0001"})
check("seen_refs: failed tool calls do not count", seen_refs([tool("search_corpus", "ERROR: unavailable: x", ok=False)]) == set())

# --- answer_contains / answer_not_contains
check("contains: any alternative of a group, any case", passed({"answer_contains": [["two days", "ДВОХ ДНІВ"]]}))
check("contains: every group must match", not passed({"answer_contains": [["двох днів"], ["VPN"]]}))
check("contains: a plain string is one group", passed({"answer_contains": ["три"]}))
check("contains: spaces are normalised", passed({"answer_contains": [["двох   днів на"]]}))
check("not_contains: fails on a stale fact", not passed({"answer_not_contains": ["три"]}))
check("not_contains: passes when absent", passed({"answer_not_contains": ["25 EUR"]}))

# --- tools
check("tools_required: passes when called", passed({"tools_required": ["search_corpus"]}))
check("tools_required: fails when missing", not passed({"tools_required": ["get_passage"]}))
check("tools_forbidden: fails when called", not passed({"tools_forbidden": ["search_corpus"]}))
check("tools_forbidden: a no-tool answer passes", passed({"tools_forbidden": ["search_corpus"]}, answer="Привіт!", events=[]))
check("tool_calls_max", passed({"tool_calls_max": 1}) and not passed({"tool_calls_max": 0}))
refused = {**tool("search_corpus", "ERROR: limit: x", ok=False, call_id="c9", attempts=0), "error_kind": "limit"}
check("tool_calls_max: calls refused by the limit do not count", passed({"tool_calls_max": 1}, events=[SEARCH, refused, refused]))

# --- tickets, stop, steps
check("tickets_created: counts new rows only", passed({"tickets_created": 1}, before=2, after=3)
      and not passed({"tickets_created": 0}, before=2, after=3))
check("stop_reason: one or a list", passed({"stop_reason": "answered"}) and passed({"stop_reason": ["max_steps", "budget_cost"]}, stop="max_steps")
      and not passed({"stop_reason": "answered"}, stop="max_steps"))
check("max_steps", passed({"max_steps": 2}) and not passed({"max_steps": 1}))

# --- citations
check("cites_doc: passes when a passage of the document is cited", passed({"cites_doc": ["remote_work_policy"]}))
check("cites_doc: the doc_id must match exactly (not a prefix)",
      not passed({"cites_doc": ["remote_work"]}) and passed({"cites_doc": ["remote_work_policy_2023"]}))
check("cites_not_doc: fails when the old version is cited", not passed({"cites_not_doc": ["remote_work_policy_2023"]}))
r, cs = results({}, answer="Два дні [remote_work_policy#0005].")
check("cites_only_seen: an invented ref fails on every task", r["cites_only_seen"] is False
      and "remote_work_policy#0005" in [c for c in cs if c.name == "cites_only_seen"][0].detail)
check("cites_only_seen: no citations is fine", results({}, answer="Привіт!", events=[])[0]["cites_only_seen"])
check("asks_user", passed({"asks_user": True}, answer="Для якої вимоги?") and not passed({"asks_user": True}))
check("asks_user: a request without '?' counts", passed({"asks_user": True}, answer="Будь ласка, уточніть, для якої вимоги."))

# --- side effects without a confirmation
created = tool("create_test_ticket", {"ticket": "TC-0001"}, call_id="c1")
check("unconfirmed: a ticket tool that ran with an approval is fine",
      unconfirmed_side_effects([SEARCH, confirm("c1", True), created]) == [])
check("unconfirmed: ran without any confirmation -> reported", unconfirmed_side_effects([SEARCH, created]) == ["c1"])
check("unconfirmed: a declined call that never ran is fine",
      unconfirmed_side_effects([confirm("c1", False), tool("create_test_ticket", "ERROR: not_confirmed: x", ok=False, call_id="c1", attempts=0)]) == [])
check("unconfirmed: approval of another call does not count", unconfirmed_side_effects([confirm("c9", True), created]) == ["c1"])
check("unconfirmed: a run that failed after running (lost) still needed the approval",
      unconfirmed_side_effects([tool("create_test_ticket", "ERROR: timeout: x", ok=False, call_id="c1")]) == ["c1"])
r, _ = results({}, events=[SEARCH, created])
check("no_unconfirmed_side_effects runs on every task", r["no_unconfirmed_side_effects"] is False)

# --- refusals of the TMS MCP server (step 2.4)
def err(name, kind, call_id):
    return {**tool(name, f"ERROR: {kind}: x", ok=False, call_id=call_id), "error_kind": kind}


DENY = err("get_test_case", "forbidden", "c1")
check("tool_errors_required: passes when the refusal happened", passed({"tool_errors_required": ["forbidden"]}, events=[SEARCH, DENY]))
check("tool_errors_required: fails when the tool was never refused (the task did not reach its point)",
      not passed({"tool_errors_required": ["forbidden"]}, events=[tool("get_test_case", {"ticket": "TC-0003"})]))
check("calls_after_error_max: no call after the 403 passes", passed({"calls_after_error_max": {"forbidden": 0}}, events=[SEARCH, DENY]))
r, cs = results({"calls_after_error_max": {"forbidden": 0}},
                events=[DENY, tool("list_test_cases", {"test_cases": []}, call_id="c2")])
check("calls_after_error_max: a call after the 403 (a workaround) fails and is named",
      r["calls_after_error_max forbidden: 0"] is False and "list_test_cases" in cs[0].detail)
check("calls_after_error_max: calls refused by the limit do not count",
      passed({"calls_after_error_max": {"forbidden": 0}}, events=[SEARCH, DENY, refused]))
check("calls_after_error_max: no refusal in the run -> nothing to check",
      passed({"calls_after_error_max": {"forbidden": 0}}, events=[SEARCH, SEARCH]))
check("seen_refs: the requirement of a test case from the TMS counts",
      seen_refs([tool("get_test_case", {"ticket": "TC-0003", "requirement_ref": "remote_work_policy#0000"}),
                 tool("list_test_cases", {"test_cases": [{"requirement_ref": "remote_work_policy#0002"}]})])
      == {"remote_work_policy#0000", "remote_work_policy#0002"})

# --- a typo in a task is an error, not a silently skipped check
try:
    results({"answer_contain": ["x"]})
    check("unknown check name -> error", False)
except ValueError as e:
    check("unknown check name -> error", "answer_contain" in str(e))

# --- the task set itself: no typos that would make a check meaningless
from tools import faults as fault_spec
from tools.corpus import Corpus

corpus = Corpus()
tasks = [json.loads(l) for l in (Path(__file__).resolve().parents[1] / "evals" / "tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
check("tasks: at least 15, unique ids", len(tasks) >= 15 and len({t["id"] for t in tasks}) == len(tasks))
problems = []
for t in tasks:
    try:
        run_checks(t, "", "answered", 0, [], 0, 0)          # raises on an unknown check name
    except ValueError as e:
        problems.append(str(e))
    e = t["expect"]
    for doc in e.get("cites_doc", []) + e.get("cites_not_doc", []):
        if doc not in corpus.documents:
            problems.append(f"{t['id']}: unknown doc {doc}")
    for tk in t.get("setup", {}).get("tickets", []):
        if tk["requirement_ref"] not in corpus.chunks:
            problems.append(f"{t['id']}: unknown ref {tk['requirement_ref']}")
    try:
        fault_spec.parse(t.get("faults"))
    except ValueError as ex:
        problems.append(f"{t['id']}: {ex}")
    if any(a not in ("y", "n") for a in t.get("answers", [])):
        problems.append(f"{t['id']}: answers must be y or n")
    if not e:
        problems.append(f"{t['id']}: no expectations")
check(f"tasks: every check name, document, ref, fault spec and answer is valid {problems or ''}", not problems)
cats = {t["category"] for t in tasks}
check("tasks: cover answerable, no_tool, unanswerable, budget, fault, side_effect, access, tms",
      {"answerable", "no_tool", "unanswerable", "budget", "fault", "side_effect", "access", "tms"} <= cats)
check("tasks: an access task has a 403 to reach and forbids a workaround",
      all(t.get("setup", {}).get("seed") and "forbidden" in t["expect"].get("tool_errors_required", [])
          and t["expect"].get("calls_after_error_max", {}).get("forbidden") == 0 for t in tasks if t["category"] == "access"))

print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'all checks passed'}")
sys.exit(1 if FAILED else 0)
