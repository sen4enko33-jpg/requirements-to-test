"""Judge the saved answers: python -m rag.eval.run_judge v1 v3_noguard ...   (names of rag/data/answers_<name>.jsonl)
Adds "judge" ({correct, faithful, reason}) to every row, prints per file: judge correctness and faithfulness, and where the
judge and the deterministic scorers disagree."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import yaml
from dotenv import load_dotenv

from .judge import JUDGE_VERSION, judge
from .run_answers import ROOT, load_testset

DATA = ROOT / "rag" / "data"


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if "error" not in r["judge"]]
    rate = lambda sel, k: round(sum(r["judge"][k] for r in sel) / len(sel), 3) if sel else None
    cat = lambda c: [r for r in ok if r["category"] == c]
    answered = [r for r in ok if r["answer"]["answered"]]
    return {"n": len(rows), "judge_errors": len(rows) - len(ok), "correct": rate(ok, "correct"),
            "correct_answerable": rate(cat("answerable"), "correct"), "correct_trap": rate(cat("trap"), "correct"),
            "correct_unanswerable": rate(cat("unanswerable"), "correct"), "faithful_answered": rate(answered, "faithful"),
            "unfaithful_ids": [r["id"] for r in answered if not r["judge"]["faithful"]],
            "disagree_with_scorers": [r["id"] for r in ok if r["judge"]["correct"] != r["scores"]["pass"]]}


def main():
    load_dotenv(ROOT / ".env"); load_dotenv(ROOT.parent / ".env")
    from ..llm import make_client
    llm = make_client(yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")), "judge")
    qs = {q["id"]: q for q in load_testset()}
    for name in sys.argv[1:]:
        path = DATA / f"answers_{name}.jsonl"
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        with ThreadPoolExecutor(6) as ex:
            verdicts = list(ex.map(lambda r: judge(llm, r["question"], qs[r["id"]]["expected_answer"], r["answer"]["text"],
                                                   r["answer"]["citations"]), rows))
        for r, v in zip(rows, verdicts):
            r["judge"], r["judge_version"] = v, JUDGE_VERSION
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        print(name, json.dumps(summarize(rows)))


if __name__ == "__main__":
    main()
