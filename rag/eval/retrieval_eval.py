"""Retrieval metrics. A retrieved chunk is relevant to a question when it comes from the question's document and contains
the evidence quote (whitespace-insensitive). This does not depend on how the document was chunked, so one question set
measures both chunkings."""
import re


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<!--.*?-->", "", text)).strip()


def is_relevant(chunk: dict, question: dict) -> bool:
    return chunk["doc_id"] == question["doc_id"] and norm(question["evidence"]) in norm(chunk["text"])


def first_relevant_rank(hits: list[dict], question: dict) -> int | None:
    """Rank (from 1) of the first relevant chunk in the hits, or None."""
    for h in hits:
        if is_relevant(h, question):
            return h["rank"]
    return None


def summarize(ranks: list[int | None], ks=(1, 3, 5, 10)) -> dict:
    """recall@k = share of questions with a relevant chunk in the top k; mrr = mean of 1/rank (0 when not found)."""
    n = len(ranks)
    out = {f"recall@{k}": sum(1 for r in ranks if r is not None and r <= k) / n for k in ks}
    out["mrr"] = sum(1 / r for r in ranks if r) / n
    return out
