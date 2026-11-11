"""Scorers of the answer test set: python tests/test_scorers.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rag.eval.run_answers import load_testset
from rag.eval.scorers import facts_found, score, summarize

fails = 0


def check(name, cond):
    global fails
    print(("ok   " if cond else "FAIL ") + name)
    fails += not cond


def A(text, docs=(), answered=True, problems=()):
    return {"answered": answered, "text": text, "citations": [{"doc_id": d} for d in docs], "problems": list(problems)}


Q = {q["id"]: q for q in load_testset()}
check("test set: 28 questions, unique ids", len(Q) == 28)
check("test set: 16 answerable, 6 trap, 6 unanswerable",
      sorted([sum(q["category"] == c for q in Q.values()) for c in ("answerable", "trap", "unanswerable")]) == [6, 6, 16])
check("test set: answerable and trap questions have sources and facts; unanswerable ones have none",
      all(q["expected_sources"] and q["key_facts"] for q in Q.values() if not q["must_refuse"])
      and all(not q["expected_sources"] and q["must_refuse"] for q in Q.values() if q["category"] == "unanswerable"))
check("a whole number is not found inside a longer one", facts_found("limit is 400 EUR", [["40"]]) == [False] and facts_found("40 EUR", [["40"]]) == [True])
check("a decimal is not cut", facts_found("availability 99.999%", [["99.999"]]) == [True] and facts_found("v 9.99", [["99.999"]]) == [False])
check("case and spaces do not matter", facts_found("Up to  TWO days", [["two days"]]) == [True])
ok = score(Q["t11"], A("It shows 10 results [1].", ["2007_e_store"]))
check("answerable: right fact and source passes", ok["pass"])
check("answerable: wrong source fails", not score(Q["t11"], A("10 [1].", ["2007_email"]))["pass"])
check("answerable: missing fact fails", not score(Q["t11"], A("Several [1].", ["2007_e_store"]))["pass"])
check("answerable: refusing fails", not score(Q["t11"], A("I don't know", answered=False))["pass"])
check("unanswerable: refusal passes", score(Q["n01"], A("I don't know", answered=False))["pass"])
check("unanswerable: a hedged refusal ending with the I-don't-know sentence passes", score(Q["n01"], A("The policy does not say it. Therefore, I don't know: the provided documents do not answer this question."))["pass"])
check("unanswerable: any answer fails", not score(Q["n01"], A("Yes [1].", ["remote_work_policy"]))["pass"])
check("trap with forbidden source: citing it fails", not score(Q["p03"], A("1/14/2004 [1][2].", ["2004_watcom", "2004_watcom_gui"]))["pass"])
check("trap with forbidden source: only the right one passes", score(Q["p03"], A("1/14/2004 [1].", ["2004_watcom"]))["pass"])
cur = score(Q["p01"], A("40 EUR [1]. The 2023 version allowed 25 EUR [2].", ["remote_work_policy", "remote_work_policy_2023"]))
check("version trap: current value first, old one mentioned: passes", cur["pass"])
old = score(Q["p01"], A("The 2023 version allowed 25 EUR [2]. The current one allows 40 EUR [1].", ["remote_work_policy", "remote_work_policy_2023"]))
check("version trap: old value first fails", not old["pass"] and not old["current"])
check("version trap: only the old value fails", not score(Q["p01"], A("25 EUR [2].", ["remote_work_policy_2023"]))["pass"])
check("current-version trap t04: the 2023 hours as the answer fail", not score(Q["t04"], A("Core hours are 11:00 to 15:00 [1]. An older version says 10:00 to 16:00 [2].", ["remote_work_policy_2023", "remote_work_policy"]))["pass"])
check("invented reference fails", not score(Q["t11"], A("10 [1].", ["2007_e_store"], problems=["invalid_reference"]))["pass"])
s = summarize([{"category": "answerable", "scores": ok}, {"category": "unanswerable", "scores": score(Q["n01"], A("x", answered=False))}])
check("summary counts per category", s["pass_answerable"] == 1.0 and s["refused_when_unanswerable"] == 1.0 and s["pass_trap"] is None)
sys.exit(1 if fails else 0)
