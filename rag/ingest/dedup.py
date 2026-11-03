"""Duplicate detection: exact duplicates (hash of the normalised text) and near duplicates (shingle overlap).

Exact duplicates are dropped from the corpus. Near duplicates (other versions, the same document in another format)
are only marked, because versions are what the test set's traps are made of.
"""
import hashlib
import re
from itertools import combinations


def normalize(md: str) -> str:
    """Lower case words only: no markup, page markers, punctuation or spacing."""
    text = re.sub(r"<!--.*?-->", " ", md).lower()
    return re.sub(r"[\W_]+", " ", text).strip()


def text_hash(md: str) -> str:
    return hashlib.sha256(normalize(md).encode("utf-8")).hexdigest()


def shingles(norm: str, k: int = 5) -> set[str]:
    words = norm.split()
    return {" ".join(words[i:i + k]) for i in range(max(len(words) - k + 1, 1))}


def find_duplicates(texts: dict[str, str], near_jaccard: float = 0.3, near_containment: float = 0.6):
    """texts: doc_id -> Markdown, in corpus order (the first of identical documents is kept).
    Returns (exact, near): exact = {duplicate_id: kept_id}; near = {doc_id: [{doc_id, jaccard, containment}]}."""
    seen: dict[str, str] = {}
    exact: dict[str, str] = {}
    for doc_id, md in texts.items():
        h = text_hash(md)
        if h in seen:
            exact[doc_id] = seen[h]
        else:
            seen[h] = doc_id
    sh = {d: shingles(normalize(md)) for d, md in texts.items() if d not in exact}
    near: dict[str, list] = {d: [] for d in texts}
    for a, b in combinations(sh, 2):
        inter = len(sh[a] & sh[b])
        if not inter:
            continue
        jac = inter / len(sh[a] | sh[b])
        cont = inter / min(len(sh[a]), len(sh[b]))
        if jac >= near_jaccard or cont >= near_containment:
            near[a].append({"doc_id": b, "jaccard": round(jac, 3), "containment": round(cont, 3)})
            near[b].append({"doc_id": a, "jaccard": round(jac, 3), "containment": round(cont, 3)})
    for d in near:
        near[d].sort(key=lambda r: -r["jaccard"])
    return exact, near
