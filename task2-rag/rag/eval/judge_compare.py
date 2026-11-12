"""Second judge from another model family, to check self-preference of the main judge (gpt-4o judges gpt-4o-mini answers).
    python -m rag.eval.judge_compare google/gemini-2.5-flash v3
Writes rag/data/judge2_<model>_<answers>.jsonl (the answers file is NOT changed) and prints the agreement with the verdicts
that are already in rag/data/answers_<answers>.jsonl (main judge)."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import yaml
from dotenv import load_dotenv

from .calibrate import kappa
from .judge import judge
from .run_answers import ROOT, load_testset

DATA = ROOT / "rag" / "data"


def main():
    model, name = sys.argv[1], sys.argv[2]
    load_dotenv(ROOT / ".env"); load_dotenv(ROOT.parent / ".env")
    from ..llm import make_client
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg["models"]["judge"]["model"] = model
    llm = make_client(cfg, "judge")
    qs = {q["id"]: q for q in load_testset()}
    rows = [json.loads(l) for l in (DATA / f"answers_{name}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    with ThreadPoolExecutor(6) as ex:
        verdicts = list(ex.map(lambda r: judge(llm, r["question"], qs[r["id"]]["expected_answer"], r["answer"]["text"],
                                               r["answer"]["citations"]), rows))
    out = DATA / f"judge2_{model.replace('/', '_')}_{name}.jsonl"
    out.write_text("".join(json.dumps({"id": r["id"], "main": r["judge"], "second": v}, ensure_ascii=False) + "\n"
                           for r, v in zip(rows, verdicts)), encoding="utf-8")
    ok = [(r, v) for r, v in zip(rows, verdicts) if "error" not in v and "error" not in r["judge"]]
    print("model", model, "judged", len(ok), "of", len(rows))
    for k in ("correct", "faithful"):
        a = [r["judge"][k] for r, _ in ok]; b = [v[k] for _, v in ok]
        print(k, "agreement", sum(x == y for x, y in zip(a, b)), "/", len(ok), "kappa", (lambda x: None if x is None else round(x, 2))(kappa(a, b)))
        print("  differ:", [(r["id"], "main=%s" % r["judge"][k], "second=%s" % v[k]) for r, v in ok if r["judge"][k] != v[k]])


if __name__ == "__main__":
    main()
