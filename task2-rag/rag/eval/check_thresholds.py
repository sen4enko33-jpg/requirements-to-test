"""Fail (exit 1) when a metric is below its threshold in rag/eval/thresholds.json. Used by CI.
  python -m rag.eval.check_thresholds retrieval            # reads rag/data/retrieval_results.json
  python -m rag.eval.check_thresholds answers v3           # scores rag/data/answers_v3.jsonl again with the scorers (no model calls)
  python -m rag.eval.check_thresholds answers-live v3      # the same scorers with the softer minimums for a fresh run with the real model
  python -m rag.eval.check_thresholds judge v3             # reads the judge verdicts that run_judge saved in answers_v3.jsonl"""
import json
import sys
from pathlib import Path

from .run_answers import load_testset
from .scorers import score, summarize as summarize_scores

DATA = Path(__file__).resolve().parents[1] / "data"
THRESHOLDS = Path(__file__).with_name("thresholds.json")


def compare(metrics: dict, minimums: dict) -> list[tuple[str, float | None, float, bool]]:
    """[(metric, value, minimum, ok)]; a metric that is missing counts as failed."""
    return [(k, metrics.get(k), m, metrics.get(k) is not None and metrics[k] >= m) for k, m in minimums.items()]


def read_rows(name: str) -> list[dict]:
    return [json.loads(l) for l in (DATA / f"answers_{name}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def metrics_for(kind: str, name: str | None, cfg: dict) -> dict:
    if kind == "retrieval":
        return json.loads((DATA / "retrieval_results.json").read_text(encoding="utf-8"))["summary"][cfg["key"]]
    rows = read_rows(name)
    if kind in ("answers", "answers-live"):
        qs = {q["id"]: q for q in load_testset()}
        for r in rows:
            r["scores"] = score(qs[r["id"]], r["answer"])
        return summarize_scores(rows)
    from .run_judge import summarize as summarize_judge
    return summarize_judge(rows)


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else ""
    if kind not in ("retrieval", "answers", "answers-live", "judge"):
        sys.exit(__doc__)
    cfg = json.loads(THRESHOLDS.read_text(encoding="utf-8"))[kind.replace("-", "_")]
    result = compare(metrics_for(kind, sys.argv[2] if len(sys.argv) > 2 else None, cfg), cfg["min"])
    for k, v, m, ok in result:
        print(f"{'ok  ' if ok else 'FAIL'} {kind}: {k} = {v} (minimum {m})")
    sys.exit(0 if all(r[3] for r in result) else 1)


if __name__ == "__main__":
    main()
