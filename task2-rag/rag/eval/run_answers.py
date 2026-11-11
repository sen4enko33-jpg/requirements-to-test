"""Run the test set through the answering pipeline and score it: python -m rag.eval.run_answers --prompt v1
Writes rag/data/answers_<prompt>.jsonl (one line per question: answer, citations, scores) and prints the summary."""
import argparse
import json
from pathlib import Path

import yaml
from dotenv import load_dotenv

from ..models import token_counter
from ..retrieval.factory import make_retriever
from .scorers import score, summarize

ROOT = Path(__file__).resolve().parents[2]
TESTSET = Path(__file__).with_name("testset.jsonl")


def load_testset() -> list[dict]:
    return [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="v1")
    ap.add_argument("--only", help="comma-separated question ids")
    ap.add_argument("--guard", choices=["on", "off"], default="on", help="off: no minimum reranker score (the model is always asked)")
    ap.add_argument("--rescore", action="store_true", help="score the saved answers again (no model calls)")
    a = ap.parse_args()
    suffix = "" if a.guard == "on" else "_noguard"
    if a.rescore:
        path = ROOT / "rag" / "data" / f"answers_{a.prompt}{suffix}.jsonl"
        qs = {q["id"]: q for q in load_testset()}
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
        for r in rows:
            r["scores"] = score(qs[r["id"]], r["answer"])
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        print(json.dumps(summarize(rows), indent=1)); print("failed:", [r["id"] for r in rows if not r["scores"]["pass"]])
        return
    load_dotenv(ROOT / ".env"); load_dotenv(ROOT.parent / ".env")
    from ..llm import make_client
    from ..answer.generate import answer_question
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    llm, tokens, retriever = make_client(cfg, "cloud"), token_counter(), make_retriever()
    qs = load_testset()
    if a.only:
        qs = [q for q in qs if q["id"] in a.only.split(",")]
    rows = []
    for q in qs:
        r = answer_question(q["question"], retriever, llm, tokens, prompt_version=a.prompt, min_score=None if a.guard == "on" else float("-inf"))
        ans = {"answered": r.answered, "text": r.text, "reason": r.reason, "citations": r.citations, "problems": r.problems,
               "passages": r.passages, "tokens_in": r.tokens_in, "tokens_out": r.tokens_out, "latency_s": r.latency_s}
        sc = score(q, ans)
        rows.append({"id": q["id"], "category": q["category"], "type": q["type"], "question": q["question"], "prompt": a.prompt, "guard": a.guard,
                     "answer": ans, "scores": sc})
        print(f"{q['id']} {'PASS' if sc['pass'] else 'FAIL'} {[k for k, v in sc.items() if not v and k != 'pass']} {r.text[:90]!r}")
    out = ROOT / "rag" / "data" / f"answers_{a.prompt}{suffix}.jsonl"
    if not a.only:
        out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps(summarize(rows), indent=1))


if __name__ == "__main__":
    main()
