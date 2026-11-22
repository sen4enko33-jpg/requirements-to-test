"""Three narrow read-only tools over the corpus of task 2: search, read a passage with its neighbours, list documents."""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from . import descriptions
from .corpus import Corpus, min_score, page_label, version_marks
from .registry import Tool, ToolInputError
from .session import Session

TEXT_CHARS = 1500          # a search result carries at most this much text (get_passage gives the full passage)
REF_PATTERN = r"^[A-Za-z0-9_.-]+#\d{4}$"
CYRILLIC = re.compile(r"[\u0400-\u04FF]")    # the documents are English: a Ukrainian query finds nothing (seen in a real run)


class SearchArgs(BaseModel):
    query: str = Field(min_length=3, max_length=300,
                       description="Short search query IN ENGLISH with the key terms (translate the question first).")
    year: Optional[int] = Field(None, ge=1990, le=2100, description="Only documents of this year (for example one policy version).")
    doc_id: Optional[str] = Field(None, max_length=80, description="Only this document (doc_id from list_documents or a result).")
    k: int = Field(5, ge=1, le=10, description="Number of passages to return.")


class PassageArgs(BaseModel):
    ref: str = Field(pattern=REF_PATTERN, description="The ref of a passage, for example remote_work_policy#0002.")
    before: int = Field(0, ge=0, le=2, description="How many previous passages of the same document to add.")
    after: int = Field(0, ge=0, le=2, description="How many next passages of the same document to add.")


class ListArgs(BaseModel):
    title_contains: Optional[str] = Field(None, min_length=2, max_length=100,
                                          description="Part of the title or of the doc_id, any case.")
    year: Optional[int] = Field(None, ge=1990, le=2100, description="Only documents of this year.")


# --- schemas of the answers: checked by the registry before an answer reaches the model, so a changed format (a renamed
# or missing field) becomes ERROR: bad_output in the trace instead of a silent None in the answer
class PassageMeta(BaseModel):
    ref: str = Field(pattern=REF_PATTERN)
    doc_id: str
    title: str
    section: str
    date: Optional[str] = None
    year: Optional[int] = None
    version: Optional[str] = None
    page: Optional[str] = None


class SearchHit(PassageMeta):
    version_mark: Optional[str] = None
    score: float
    text: str
    truncated: bool


class SearchOutput(BaseModel):
    query: str
    filters: dict
    results: list[SearchHit]
    note: Optional[str] = None


class Passage(PassageMeta):
    text: str


class PassageOutput(BaseModel):
    passages: list[Passage] = Field(min_length=1)


class DocumentRow(BaseModel):
    doc_id: str
    title: Optional[str] = None
    year: Optional[int] = None
    date: Optional[str] = None
    version: Optional[str] = None
    words: Optional[int] = None
    near_duplicates: list[str]


class ListOutput(BaseModel):
    total: int
    documents: list[DocumentRow]


def _meta(c: dict) -> dict:
    return {"ref": c["chunk_id"], "doc_id": c["doc_id"], "title": c["title"], "section": c["section"], "date": c.get("date"),
            "year": c.get("year"), "version": c.get("version"), "page": page_label(c) or None}


def make_corpus_tools(corpus: Corpus | None = None, floor: float | None = "default", session: Session | None = None) -> list[Tool]:
    """floor: drop hits whose reranker score is below it ("default" = MIN_SCORE of task 2; None = keep all).
    session: records the refs returned to the model (create_test_ticket accepts only those)."""
    corpus = corpus or Corpus()
    session = session if session is not None else Session()
    score_floor = min_score() if floor == "default" else floor

    def search_corpus(a: SearchArgs) -> dict:
        if CYRILLIC.search(a.query):
            raise ToolInputError("the query must be in English (the documents are English); translate it and call again")
        if a.doc_id is not None and a.doc_id not in corpus.documents:
            raise ToolInputError(f"unknown doc_id {a.doc_id!r}; call list_documents to see the doc_ids")
        filters = {k: v for k, v in (("year", a.year), ("doc_id", a.doc_id)) if v is not None} or None
        hits = corpus.retriever.search(a.query, a.k, "hybrid_rerank", filters)
        relevant = [h for h in hits if score_floor is None or h["score"] >= score_floor]
        marks = version_marks(relevant)
        results = [{**_meta(h), "version_mark": marks.get(h["doc_id"]), "score": round(h["score"], 2),
                    "text": h["text"][:TEXT_CHARS], "truncated": len(h["text"]) > TEXT_CHARS} for h in relevant]
        session.saw(r["ref"] for r in results)
        out = {"query": a.query, "filters": filters or {}, "results": results}
        if not results:
            out["note"] = ("nothing relevant found" + (f" ({len(hits)} weak hits dropped)" if hits else "")
                           + "; rephrase at most once, otherwise say the documents do not cover the question")
        return out

    def get_passage(a: PassageArgs) -> dict:
        c = corpus.chunks.get(a.ref)
        if c is None:
            raise ToolInputError(f"unknown ref {a.ref!r}; use a ref returned by search_corpus")
        chain, cur = [], c
        for _ in range(a.before):
            cur = corpus.chunks.get(cur.get("prev_id") or "")
            if cur is None:
                break
            chain.insert(0, cur)
        chain.append(c)
        cur = c
        for _ in range(a.after):
            cur = corpus.chunks.get(cur.get("next_id") or "")
            if cur is None:
                break
            chain.append(cur)
        session.saw(x["chunk_id"] for x in chain)
        return {"passages": [{**_meta(x), "text": x["text"]} for x in chain]}

    def list_documents(a: ListArgs) -> dict:
        docs = [d for d in corpus.documents.values()
                if (a.title_contains is None or a.title_contains.lower() in f"{d.get('title') or ''} {d['doc_id']}".lower())
                and (a.year is None or d.get("year") == a.year)]
        rows = [{"doc_id": d["doc_id"], "title": d.get("title"), "year": d.get("year"), "date": d.get("date"),
                 "version": d.get("version"), "words": d.get("words"),
                 "near_duplicates": [n["doc_id"] if isinstance(n, dict) else n for n in d.get("near_duplicates") or []]}
                for d in sorted(docs, key=lambda d: d["doc_id"])]
        return {"total": len(rows), "documents": rows}

    def tool(name, args, fn, output):
        return Tool(name, descriptions.description(name), args, fn, safe=True, side_effect=False,
                    version=descriptions.version(name), output_model=output)

    return [tool("search_corpus", SearchArgs, search_corpus, SearchOutput),
            tool("get_passage", PassageArgs, get_passage, PassageOutput),
            tool("list_documents", ListArgs, list_documents, ListOutput)]
