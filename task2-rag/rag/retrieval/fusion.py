"""Reciprocal rank fusion: several ranked lists -> one list, using positions only (no score scale, no weights to tune)."""


def rrf(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """score(id) = sum over lists of 1 / (k + position), position starting at 1. Ties are broken by id (deterministic)."""
    score: dict[str, float] = {}
    for ranking in rankings:
        for pos, cid in enumerate(ranking, start=1):
            score[cid] = score.get(cid, 0.0) + 1.0 / (k + pos)
    return sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))
