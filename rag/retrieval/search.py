"""Search over chunks: vector, hybrid (BM25 + vector with RRF) and hybrid + reranking. All modes take the same filters."""
from rank_bm25 import BM25Okapi

from .fusion import rrf
from .text import matches, tokenize

MODES = ("vector", "hybrid", "hybrid_rerank")


class Retriever:
    """chunks: list of chunk dicts; store: Store; embed_query: str -> vector; rerank: (query, [text]) -> [score] or None.

    candidates: how many chunks every ranker (vector, BM25) contributes to the fusion.
    rerank_top: how many fused chunks the reranker re-orders (the rest is dropped).
    """

    def __init__(self, chunks: list[dict], store, embed_query, rerank=None, rrf_k: int = 60,
                 candidates: int = 50, rerank_top: int = 20):
        self.chunks = {c["chunk_id"]: c for c in chunks}
        self.order = [c["chunk_id"] for c in chunks]
        self.store, self.embed_query, self.rerank = store, embed_query, rerank
        self.rrf_k, self.candidates, self.rerank_top = rrf_k, candidates, rerank_top
        # BM25 sees the section path as well: a question often repeats a heading
        self.bm25 = BM25Okapi([tokenize(" ".join(c["sections"]) + " " + c["text"]) for c in chunks])

    def _vector(self, query: str, n: int, filters) -> list[str]:
        return [cid for cid, _ in self.store.query(self.embed_query(query), n, filters)]

    def _bm25(self, query: str, n: int, filters) -> list[str]:
        scores = self.bm25.get_scores(tokenize(query))
        ranked = sorted(((s, cid) for s, cid in zip(scores, self.order) if s > 0 and matches(self.chunks[cid], filters)),
                        key=lambda p: (-p[0], p[1]))
        return [cid for _, cid in ranked[:n]]

    def search(self, query: str, k: int = 10, mode: str = "hybrid_rerank", filters: dict | None = None) -> list[dict]:
        """The k best chunks as dicts: the chunk fields plus `rank` (from 1), `score` and `mode`."""
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}, expected one of {MODES}")
        if mode == "vector":
            scored = self.store.query(self.embed_query(query), k, filters)
        else:
            fused = rrf([self._vector(query, self.candidates, filters), self._bm25(query, self.candidates, filters)], self.rrf_k)
            if mode == "hybrid":
                scored = fused[:k]
            else:
                if self.rerank is None:
                    raise ValueError("mode hybrid_rerank needs a reranker")
                top = fused[:max(self.rerank_top, k)]
                scores = self.rerank(query, [self.chunks[cid]["text"] for cid, _ in top])
                scored = sorted(((cid, float(s)) for (cid, _), s in zip(top, scores)), key=lambda p: (-p[1], p[0]))[:k]
        return [{**self.chunks[cid], "rank": r, "score": float(s), "mode": mode} for r, (cid, s) in enumerate(scored, start=1)]
