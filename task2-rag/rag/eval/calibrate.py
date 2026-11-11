"""Calibration of the LLM judge against answers rated by hand.
  python -m rag.eval.calibrate build    # picks the answers (SELECTION) into rag/eval/calibration/items.jsonl
  python -m rag.eval.calibrate judge [v1|v2]   # the judge model rates the items -> calibration/judge_<version>.jsonl
  python -m rag.eval.calibrate score [v1|v2]   # agreement between calibration/human.jsonl and calibration/judge_<version>.jsonl
human.jsonl: {"id", "correct"} per item (the user rated only correctness; "faithful" is used when present)."""
import json
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .judge import JUDGE_VERSION, judge
from .run_answers import ROOT, load_testset

DIR = Path(__file__).with_name("calibration")
DATA = ROOT / "rag" / "data"
# (answers file, question id): chosen to mix good answers, wrong ones, refusals and answers that cite badly
SELECTION = [("v1", "t01"), ("v1", "t03"), ("v1", "t12"), ("v2", "t04"), ("v2", "t10"), ("v3", "n03"), ("v1", "t15"),
             ("v3", "p01"), ("v1", "n01"), ("v2", "t01"), ("v1", "t13"), ("v1", "p05")]


def read(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def kappa(a: list[bool], b: list[bool]) -> float | None:
    """Cohen's kappa of two lists of yes/no verdicts; None when chance agreement is 1 (one class only)."""
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def agreement(human: list[dict], judged: list[dict]) -> dict:
    h, j = {x["id"]: x for x in human}, {x["id"]: x for x in judged if "error" not in x}
    ids = [i for i in h if i in j]
    out = {"n": len(ids)}
    for key in [k for k in ("correct", "faithful") if all(k in x for x in human)]:
        a, b = [bool(h[i][key]) for i in ids], [bool(j[i][key]) for i in ids]
        out[key] = {"agreement": round(sum(x == y for x, y in zip(a, b)) / len(ids), 3), "kappa": kappa(a, b),
                    "disagree": [i for i, x, y in zip(ids, a, b) if x != y]}
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    qs = {q["id"]: q for q in load_testset()}
    if cmd == "build":
        DIR.mkdir(exist_ok=True)
        items = []
        for k, (ver, qid) in enumerate(SELECTION, 1):
            row = next(r for r in read(DATA / f"answers_{ver}.jsonl") if r["id"] == qid)
            items.append({"id": f"c{k:02d}", "run": ver, "qid": qid, "question": row["question"], "reference": qs[qid]["expected_answer"],
                          "answer": row["answer"]["text"], "citations": row["answer"]["citations"]})
        (DIR / "items.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
        print(len(items), "items")
    elif cmd == "judge":
        load_dotenv(ROOT / ".env"); load_dotenv(ROOT.parent / ".env")
        from ..llm import make_client
        llm = make_client(yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")), "judge")
        ver = sys.argv[2] if len(sys.argv) > 2 else JUDGE_VERSION
        out = []
        for i in read(DIR / "items.jsonl"):
            v = judge(llm, i["question"], i["reference"], i["answer"], i["citations"], ver)
            out.append({"id": i["id"], **v}); print(i["id"], v)
        (DIR / f"judge_{ver}.jsonl").write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in out), encoding="utf-8")
    elif cmd == "score":
        print(json.dumps(agreement(read(DIR / "human.jsonl"), read(DIR / f"judge_{sys.argv[2] if len(sys.argv) > 2 else JUDGE_VERSION}.jsonl")), indent=1))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
