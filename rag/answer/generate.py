"""Question -> search -> context -> model -> checked answer with citations."""
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ValidationError

from . import settings
from .citations import IDK, check, is_idk
from .context import build_context, page_label
from .prompts import build_prompt


class RagAnswer(BaseModel):
    answer: str = Field(description="The answer; every fact sentence ends with [n] references to the passages.")
    sources: list[int] = Field(description="Numbers of the passages used in the answer.")


@dataclass
class Answer:
    question: str
    text: str                              # the answer shown to the user ("" when the model failed)
    answered: bool                         # False for "I don't know" and for failures
    reason: str                            # answered | no_hits | below_threshold | model_idk | model_error
    citations: list[dict] = field(default_factory=list)     # [{n, chunk_id, doc_id, title, section, version, date, page}]
    problems: list[str] = field(default_factory=list)       # invalid_reference | sources_mismatch | uncited_sentence
    passages: list[str] = field(default_factory=list)       # chunk ids that were in the context
    prompt_version: str = settings.PROMPT_VERSION
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_s: float | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """No invented references and no model failure."""
        return "invalid_reference" not in self.problems and self.reason != "model_error"


def _idk(question: str, reason: str, **kw) -> Answer:
    return Answer(question, IDK, False, reason, **kw)


def _citation(n: int, chunk: dict) -> dict:
    return {"n": n, "chunk_id": chunk["chunk_id"], "doc_id": chunk["doc_id"], "title": chunk["title"], "section": chunk["section"],
            "version": chunk.get("version"), "date": chunk.get("date"), "year": chunk.get("year"), "page": page_label(chunk) or None}


def answer_question(question: str, retriever, llm, tokens, filters: dict | None = None, prompt_version: str | None = None,
                    budget: int | None = None, min_score: float | None = None, k: int | None = None) -> Answer:
    """retriever: .search(query, k, mode, filters); llm: .generate(prompt, model, sampling) -> GenResult;
    tokens: text -> number of tokens (the context budget is counted with it)."""
    version = prompt_version or settings.PROMPT_VERSION
    floor = settings.MIN_SCORE if min_score is None else min_score
    hits = retriever.search(question, k or settings.TOP_K, "hybrid_rerank", filters)
    if not hits:
        return _idk(question, "no_hits", prompt_version=version)
    if floor is not None and hits[0]["score"] < floor:
        return _idk(question, "below_threshold", prompt_version=version)
    context, used = build_context(hits, budget or settings.CONTEXT_BUDGET_TOKENS, tokens)
    if not used:
        return _idk(question, "no_hits", prompt_version=version)
    prompt = build_prompt(version, context, question)

    parsed, res = None, None
    for attempt in range(2):                      # one repeat when the output is not valid JSON of the right shape
        res = llm.generate(prompt if attempt == 0 else prompt + "\n\nReply with valid JSON only.", RagAnswer, settings.SAMPLING)
        if not res.text:                          # the client failed (it has its own retries): do not repeat
            break
        try:
            parsed = RagAnswer.model_validate_json(res.text)
            break
        except ValidationError:
            continue
    meta = dict(prompt_version=version, passages=[u["chunk"]["chunk_id"] for u in used], tokens_in=res.tokens_in,
                tokens_out=res.tokens_out, latency_s=res.latency_s)
    if parsed is None:
        return Answer(question, "", False, "model_error", error=res.error or "output is not valid JSON", **meta)
    if is_idk(parsed.answer):
        return Answer(question, IDK, False, "model_idk", **meta)
    c = check(parsed.answer, parsed.sources, len(used))
    problems = (["invalid_reference"] if c["invalid"] else []) + (["sources_mismatch"] if c["sources_mismatch"] else []) \
        + (["uncited_sentence"] if c["uncited_sentences"] else [])
    by_n = {u["n"]: u["chunk"] for u in used}
    return Answer(question, parsed.answer, True, "answered", [_citation(n, by_n[n]) for n in c["cited"]], problems, **meta)
