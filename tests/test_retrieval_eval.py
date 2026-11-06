"""Checks of the retrieval metrics: python tests/test_retrieval_eval.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.eval.retrieval_eval import first_relevant_rank, is_relevant, summarize

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


q = {"doc_id": "a", "evidence": "may work remotely up to two days."}
check("relevant: same document and quote", is_relevant({"doc_id": "a", "text": "Staff   may work\nremotely up to two days. More."}, q))
check("not relevant: other document with the same quote", not is_relevant({"doc_id": "b", "text": "may work remotely up to two days."}, q))
check("not relevant: same document, no quote", not is_relevant({"doc_id": "a", "text": "may work remotely up to three days."}, q))
check("page markers do not break the quote", is_relevant({"doc_id": "a", "text": "may work remotely <!-- page 2 --> up to two days."}, q))
hits = [{"doc_id": "a", "text": "x", "rank": 1}, {"doc_id": "b", "text": "may work remotely up to two days.", "rank": 2},
        {"doc_id": "a", "text": "may work remotely up to two days.", "rank": 3}]
check("first relevant rank", first_relevant_rank(hits, q) == 3 and first_relevant_rank(hits[:2], q) is None)
s = summarize([1, 2, None, 4])
check("recall@k", s["recall@1"] == 0.25 and s["recall@3"] == 0.5 and s["recall@5"] == 0.75 and s["recall@10"] == 0.75)
check("mrr", abs(s["mrr"] - (1 + 0.5 + 0 + 0.25) / 4) < 1e-12)
check("summary of perfect and empty", summarize([1, 1])["mrr"] == 1.0 and summarize([None])["recall@10"] == 0.0)
print("\n%d failed" % len(FAILED) if FAILED else "\nall ok")
sys.exit(1 if FAILED else 0)
