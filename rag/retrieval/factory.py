"""The search used by the answering step and by the CLI (Chroma + BM25 + reranker, configuration of rag.eval.run_retrieval)."""
from pathlib import Path

from ..models import embed_fns, reranker
from .build import client
from .search import Retriever
from .store import Store, load_chunks

DATA = Path(__file__).resolve().parents[1] / "data"


def make_retriever(strategy: str = "structural") -> Retriever:
    coll, fname = ("chunks_structural", "chunks.jsonl") if strategy == "structural" else ("chunks_fixed", "chunks_fixed.jsonl")
    _, embed_query = embed_fns()
    return Retriever(load_chunks(DATA / fname), Store(client(), coll), embed_query, reranker(), 60, 50, 20)
