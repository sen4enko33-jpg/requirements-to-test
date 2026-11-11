"""Compare search configurations on the labelled questions: python -m rag.eval.run_retrieval
Writes rag/data/retrieval_results.md and rag/data/retrieval_results.json. The configurations are fixed in CONFIG; they are
not tuned on these questions."""
import json
from pathlib import Path

from ..models import embed_fns, reranker
from ..retrieval.build import client
from ..retrieval.search import MODES, Retriever
from ..retrieval.store import Store, load_chunks
from .retrieval_eval import first_relevant_rank, is_relevant, summarize

DATA = Path(__file__).resolve().parents[1] / "data"
QUESTIONS = Path(__file__).resolve().parent / "retrieval_questions.jsonl"
CONFIG = {"k": 10, "candidates": 50, "rrf_k": 60, "rerank_top": 20}
INDEXES = {"structural-v1": ("chunks_structural", "chunks.jsonl"), "fixed-300": ("chunks_fixed", "chunks_fixed.jsonl")}


def main():
    qs = [json.loads(l) for l in QUESTIONS.read_text(encoding="utf-8").splitlines() if l.strip()]
    _, embed_query = embed_fns()
    rerank = reranker()
    ranks = {}                                    # (strategy, mode) -> [rank or None per question]
    for strategy, (coll, fname) in INDEXES.items():
        chunks = load_chunks(DATA / fname)
        missing = [q["id"] for q in qs if not any(is_relevant(c, q) for c in chunks)]
        if missing:
            print(f"WARNING {strategy}: no relevant chunk exists for {missing}")
        r = Retriever(chunks, Store(client(), coll), embed_query, rerank, CONFIG["rrf_k"], CONFIG["candidates"], CONFIG["rerank_top"])
        for mode in MODES:
            ranks[(strategy, mode)] = [first_relevant_rank(r.search(q["question"], CONFIG["k"], mode), q) for q in qs]
    res = {f"{s}|{m}": summarize(v) for (s, m), v in ranks.items()}
    out = ["# Retrieval results", "", f"{len(qs)} hand-checked questions (`rag/eval/retrieval_questions.jsonl`). A chunk is relevant when it comes from "
           "the question's document and contains the evidence quote. Configuration (fixed before the run): "
           f"top {CONFIG['k']}, {CONFIG['candidates']} candidates from each of vector and BM25, RRF k={CONFIG['rrf_k']}, "
           f"the reranker re-orders the top {CONFIG['rerank_top']}.", "",
           "| chunking | search | recall@1 | recall@3 | recall@5 | recall@10 | MRR |", "|---|---|---|---|---|---|---|"]
    for (s, m) in ranks:
        x = res[f"{s}|{m}"]
        out.append(f"| {s} | {m} | " + " | ".join(f"{x[k]:.2f}" for k in ("recall@1", "recall@3", "recall@5", "recall@10", "mrr")) + " |")
    out += ["", "Rank of the first relevant chunk per question (`-` = not in the top 10):", ""]
    cols = list(ranks)
    out += ["| id | type | document | " + " | ".join(f"{s[:5]} {m}" for s, m in cols) + " |", "|---|---|---|" + "---|" * len(cols)]
    for i, q in enumerate(qs):
        out.append(f"| {q['id']} | {q['type']} | {q['doc_id']} | " + " | ".join(str(ranks[c][i] or "-") for c in cols) + " |")
    (DATA / "retrieval_results.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    (DATA / "retrieval_results.json").write_text(json.dumps({"config": CONFIG, "summary": res, "questions": [q["id"] for q in qs],
        "ranks": {f"{s}|{m}": v for (s, m), v in ranks.items()}}, indent=2) + "\n", encoding="utf-8")
    print("\n".join(out[:14]))


if __name__ == "__main__":
    main()
