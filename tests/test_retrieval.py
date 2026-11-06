"""Checks of the search (Chroma in memory, a fake embedding model, no network): python tests/test_retrieval.py"""
import hashlib
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chromadb

from rag.retrieval.fusion import rrf
from rag.retrieval.search import Retriever
from rag.retrieval.store import Store, chunks_sha
from rag.retrieval.text import matches, tokenize

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


# --- text helpers
check("tokenize: lower case, stop words dropped", tokenize("The Policy of the Company") == ["policy", "company"])
check("tokenize: identifiers stay whole", tokenize("see REQ-12 and i86obj.c") == ["see", "req-12", "i86obj.c"])
meta = {"doc_id": "a", "year": 2004, "version": "1.0"}
check("filter: equal", matches(meta, {"doc_id": "a"}) and not matches(meta, {"doc_id": "b"}))
check("filter: list = any of", matches(meta, {"doc_id": ["x", "a"]}) and not matches(meta, {"doc_id": ["x", "y"]}))
check("filter: all fields must match", matches(meta, {"doc_id": "a", "year": 2004}) and not matches(meta, {"doc_id": "a", "year": 2005}))
check("filter: none = everything", matches(meta, None) and matches(meta, {}))
check("filter: missing field does not match", not matches(meta, {"date": "2004-01-01"}))

# --- fusion
r = rrf([["a", "b", "c"], ["c", "a", "d"]])
check("rrf: ids in both lists come first", [i for i, _ in r][:2] == ["a", "c"] and {i for i, _ in r} == {"a", "b", "c", "d"})
check("rrf: formula", abs(dict(r)["a"] - (1 / 61 + 1 / 62)) < 1e-12)
check("rrf: ties broken by id", [i for i, _ in rrf([["z"], ["a"]])] == ["a", "z"])
check("rrf: empty", rrf([[], []]) == [])


# --- fake embedding model: hashed bag of words, normalised
def vec(text, dim=128):
    v = [0.0] * dim
    for t in tokenize(text):
        v[int(hashlib.md5(t.encode()).hexdigest(), 16) % dim] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


CALLS = []


def embed_docs(texts):
    CALLS.append(len(texts))
    return [vec(t) for t in texts]


def mk(i, doc, text, year=2004, version="1.0", section="Sec"):
    return {"chunk_id": f"{doc}#{i:04d}", "doc_id": doc, "title": doc, "year": year, "version": version, "date": None,
            "source_file": f"{doc}.pdf", "section": section, "sections": [section], "position": i, "n_words": len(text.split()),
            "sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text}


CH = [
    mk(0, "policy_a", "Employees may work remotely two days per week after the probation period.", year=2025, version="2.0", section="Remote work"),
    mk(1, "policy_a", "Company laptops must use full disk encryption and the corporate VPN.", year=2025, version="2.0", section="Security"),
    mk(2, "policy_b", "Employees may work remotely three days per week after the probation period.", year=2020, version="1.0", section="Remote work"),
    mk(3, "policy_b", "Expense claims for a keyboard are limited to forty euro per year.", year=2020, version="1.0", section="Equipment"),
    mk(4, "log", "i86obj.c: NeedMore(arr,more=00000001(1)) i86obj.c: OutOffset(value=0)", year=2004, section="Trace"),
    mk(5, "log", "The scheduler assigns every task to a worker thread in round robin order.", year=2004, section="Scheduler"),
]
client = chromadb.EphemeralClient()
store = Store.ensure(client, "t_main", CH, embed_docs, model="fake")
ret = Retriever(CH, store, lambda q: vec(q), rerank=lambda q, texts: [len(set(tokenize(q)) & set(tokenize(t))) for t in texts],
                candidates=10, rerank_top=4)

# --- vector
h = ret.search("full disk encryption VPN", k=3, mode="vector")
check("vector: the closest chunk first", h[0]["chunk_id"] == "policy_a#0001")
check("vector: ranks start at 1 and scores fall", [x["rank"] for x in h] == [1, 2, 3] and h[0]["score"] >= h[1]["score"] >= h[2]["score"])
check("vector: k larger than the corpus", len(ret.search("remote", k=50, mode="vector")) == len(CH))
check("vector: hits carry the chunk metadata", h[0]["doc_id"] == "policy_a" and h[0]["section"] == "Security" and "text" in h[0])

# --- filters in every mode
for mode in ("vector", "hybrid", "hybrid_rerank"):
    hs = ret.search("remote days per week probation", k=6, mode=mode, filters={"doc_id": "policy_b"})
    check(f"filter doc_id [{mode}]", hs and all(x["doc_id"] == "policy_b" for x in hs))
    hs = ret.search("remote days per week probation", k=6, mode=mode, filters={"year": 2025})
    check(f"filter year [{mode}]", hs and all(x["year"] == 2025 for x in hs))
    hs = ret.search("remote days", k=6, mode=mode, filters={"doc_id": ["policy_a", "log"], "year": 2025})
    check(f"filter list + second field [{mode}]", hs and all(x["doc_id"] == "policy_a" for x in hs))
    check(f"filter with no match gives nothing [{mode}]", ret.search("remote", k=5, mode=mode, filters={"doc_id": "nope"}) == [])

# --- the trap pair: the filter picks the version
a = ret.search("remote days per week", k=1, mode="hybrid", filters={"version": "2.0"})[0]
b = ret.search("remote days per week", k=1, mode="hybrid", filters={"version": "1.0"})[0]
check("version filter picks the right twin", a["doc_id"] == "policy_a" and b["doc_id"] == "policy_b")

# --- hybrid: BM25 finds an exact identifier
q = "i86obj.c"
check("hybrid: an exact identifier is found", ret.search(q, k=1, mode="hybrid")[0]["chunk_id"] == "log#0004")
check("hybrid: contains vector hits too", {x["chunk_id"] for x in ret.search("scheduler worker thread", k=3, mode="hybrid")} >= {"log#0005"})
check("hybrid: no duplicates", len({x["chunk_id"] for x in ret.search("remote work", k=6, mode="hybrid")}) == len(ret.search("remote work", k=6, mode="hybrid")))

# --- rerank
hr = ret.search("keyboard expense claims euro", k=2, mode="hybrid_rerank")
check("rerank: re-orders by the reranker score", hr[0]["chunk_id"] == "policy_b#0003" and hr[0]["score"] >= hr[1]["score"])
check("rerank: at most k results", len(ret.search("remote work", k=2, mode="hybrid_rerank")) == 2)
seen = []
r2 = Retriever(CH, store, lambda q: vec(q), rerank=lambda q, t: (seen.append(len(t)), [0.0] * len(t))[1], candidates=10, rerank_top=3)
r2.search("remote work", k=2, mode="hybrid_rerank")
check("rerank: only rerank_top chunks are scored", seen == [3])
try:
    Retriever(CH, store, lambda q: vec(q)).search("x", mode="hybrid_rerank"); ok = False
except ValueError:
    ok = True
check("rerank: without a reranker it is an error", ok)
try:
    ret.search("x", mode="magic"); ok = False
except ValueError:
    ok = True
check("unknown mode is an error", ok)

# --- determinism and index reuse
check("deterministic", [x["chunk_id"] for x in ret.search("remote work", 5, "hybrid_rerank")] == [x["chunk_id"] for x in ret.search("remote work", 5, "hybrid_rerank")])
n = len(CALLS)
Store.ensure(client, "t_main", CH, embed_docs, model="fake")
check("index is reused when nothing changed", len(CALLS) == n)
Store.ensure(client, "t_main", CH[:5], embed_docs, model="fake")
check("index is rebuilt when the chunks change", len(CALLS) > n and Store(client, "t_main").collection.count() == 5)
n = len(CALLS)
Store.ensure(client, "t_main", CH[:5], embed_docs, model="other")
check("index is rebuilt when the model changes", len(CALLS) > n)
check("chunks_sha changes with the text", chunks_sha(CH) != chunks_sha(CH[:5]))

# --- an interrupted build is resumed
import time
c2 = chromadb.EphemeralClient()
n0 = len(CALLS)
st = Store.ensure(c2, "t_resume", CH, embed_docs, model="fake", batch=2, deadline=time.time() - 1)
check("resume: a build stopped by the deadline is incomplete", not st.is_complete and st.collection.count() == 0)
c2.get_collection("t_resume").add(ids=[CH[0]["chunk_id"]], embeddings=[vec(CH[0]["text"])], documents=[CH[0]["text"]], metadatas=[{"doc_id": "policy_a"}])
n1 = len(CALLS)
st = Store.ensure(c2, "t_resume", CH, embed_docs, model="fake", batch=2)
check("resume: only the missing chunks are embedded", st.is_complete and sum(CALLS[n1:]) == len(CH) - 1)

print("\n%d failed" % len(FAILED) if FAILED else "\nall ok")
sys.exit(1 if FAILED else 0)
