"""Checks of the answering step with a fake search and a fake model (no network): python tests/test_answer.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.clients.base import GenResult

from rag.answer import settings
from rag.answer.citations import IDK, check as cite_check, cited_numbers, is_idk, sentences
from rag.answer.context import build_context, header
from rag.answer.generate import answer_question
from rag.answer.prompts import build_prompt, load_template

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


tok = lambda t: len(t.split())


def chunk(i, text, doc="pol", title="Policy", year=2026, date="2026-01-15", version=None, section="1. Purpose", page=(1, 1), score=5.0):
    return {"chunk_id": f"{doc}#{i:04d}", "doc_id": doc, "title": title, "year": year, "date": date, "version": version,
            "section": section, "page_start": page[0], "page_end": page[1], "text": text, "score": score, "rank": i + 1}


# --- header and context
c = chunk(0, "x", version="2.0")
check("header: all fields", header(c, 2) == "[2] Policy (pol), version 2.0, effective 2026-01-15, section: 1. Purpose, page 1")
check("header: year when there is no date, no page for non-PDF", header(chunk(0, "x", date=None, page=(None, None)), 1) == "[1] Policy (pol), year 2026, section: 1. Purpose")
check("header: page range", header(chunk(0, "x", page=(2, 3)), 1).endswith("pages 2-3"))
hits = [chunk(0, "a " * 40), chunk(1, "b " * 40), chunk(2, "c " * 40)]
ctx, used = build_context(hits, 1000, tok)
check("context: all chunks, numbered 1..N", [u["n"] for u in used] == [1, 2, 3] and "[3] Policy" in ctx)
ctx, used = build_context(hits, 70, tok)
check("context: budget respected, chunks whole", len(used) == 1 and tok(ctx) <= 70 and ctx.count("a ") == 39)   # 40 words, the last without a trailing space
hits2 = [chunk(0, "a " * 90), chunk(1, "b " * 90), chunk(2, "c " * 5)]
ctx, used = build_context(hits2, 130, tok)
check("context: a small chunk further down still fits; numbers follow the used order", [u["chunk"]["chunk_id"] for u in used] == ["pol#0000", "pol#0002"] and "[2] Policy" in ctx)
check("context: no hits", build_context([], 100, tok) == ("", []))

# --- prompt
t = load_template("v1")
check("prompt: the rules mention references, don't know and versions", "[2]" in t and IDK in t and "newest version" in t)
p = build_prompt("v1", "CONTEXT <<QUESTION>>", "What is <<CONTEXT>>?")
check("prompt: one pass, placeholders inside the texts stay literal", "CONTEXT <<QUESTION>>" in p and "What is <<CONTEXT>>?" in p)
try:
    build_prompt("v99", "c", "q"); ok = False
except FileNotFoundError:
    ok = True
check("prompt: unknown version is an error", ok)

# --- citations
check("cited: order, no repeats", cited_numbers("A [2][1]. B [2][12].") == [2, 1, 12])
check("sentences: a reference after the full stop stays with its sentence", sentences("Two days. [1] Next one [2].") == ["Two days[1].", "Next one [2]."])
r = cite_check("It is two days [1]. It is not allowed.", [1], 2)
check("check: an uncited fact sentence is found", r["uncited_sentences"] == ["It is not allowed."] and not r["invalid"])
check("check: an invented reference is found", cite_check("Two days [3].", [3], 2)["invalid"] == [3])
check("check: sources must match the references", cite_check("Two days [1].", [2], 2)["sources_mismatch"] and not cite_check("Two days [1].", [1], 2)["sources_mismatch"])
check("idk detection", is_idk(IDK) and is_idk("  I don't know.") and not is_idk("The policy says I don't know"))


# --- answer_question
class FakeSearch:
    def __init__(self, hits):
        self.hits, self.calls = hits, []

    def search(self, q, k, mode, filters=None):
        self.calls.append((q, k, mode, filters))
        return self.hits


class FakeLLM:
    def __init__(self, *outputs):
        self.outputs, self.prompts, self.samplings = list(outputs), [], []

    def generate(self, prompt, model, sampling):
        self.prompts.append(prompt)
        self.samplings.append(sampling)
        o = self.outputs.pop(0)
        return GenResult(o if isinstance(o, str) or o is None else json.dumps(o), 1.5, 100, 20, 1, None if o else "boom")


H = [chunk(0, "Staff may work remotely up to two days per week.", section="2. Eligibility"), chunk(1, "Laptops use encryption.", section="5. Security", page=(2, 2), score=3.0)]
good = {"answer": "Up to two days per week [1].", "sources": [1]}

s, l = FakeSearch([]), FakeLLM()
a = answer_question("q", s, l, tok)
check("no hits: I don't know, the model is not called", not a.answered and a.reason == "no_hits" and a.text == IDK and not l.prompts)
s, l = FakeSearch(H), FakeLLM()
a = answer_question("q", s, l, tok, min_score=9.0)
check("score below the threshold: I don't know, the model is not called", a.reason == "below_threshold" and not l.prompts)
s, l = FakeSearch(H), FakeLLM(good)
a = answer_question("How many days?", s, l, tok, filters={"year": 2026})
check("answer: text, reason, no problems", a.answered and a.reason == "answered" and a.text == good["answer"] and a.problems == [] and a.ok)
check("answer: one call, temperature 0, context and question in the prompt", len(l.prompts) == 1 and l.samplings[0]["temperature"] == 0.0
      and "[1] Policy (pol)" in l.prompts[0] and "Question: How many days?" in l.prompts[0])
check("answer: search mode, k and filters", s.calls == [("How many days?", settings.TOP_K, "hybrid_rerank", {"year": 2026})])
check("answer: citation with document, section, date", a.citations == [{"n": 1, "chunk_id": "pol#0000", "doc_id": "pol", "title": "Policy", "section": "2. Eligibility",
      "version": None, "date": "2026-01-15", "year": 2026, "page": "page 1"}])
check("answer: usage and the chunks in the context", a.tokens_in == 100 and a.tokens_out == 20 and a.passages == ["pol#0000", "pol#0001"])
a = answer_question("q", FakeSearch(H), FakeLLM({"answer": IDK, "sources": []}), tok)
check("model says I don't know", not a.answered and a.reason == "model_idk" and a.citations == [])
a = answer_question("q", FakeSearch(H), FakeLLM({"answer": "Two days [5].", "sources": [5]}), tok)
check("invented reference: flagged, not turned into a citation", "invalid_reference" in a.problems and not a.ok and a.citations == [])
a = answer_question("q", FakeSearch(H), FakeLLM({"answer": "Two days [1]. Also three hours.", "sources": [1]}), tok)
check("uncited sentence is reported", "uncited_sentence" in a.problems and a.ok)
l = FakeLLM("not json", good)
a = answer_question("q", FakeSearch(H), l, tok)
check("not JSON: one repeat with a reminder, then fine", a.answered and len(l.prompts) == 2 and l.prompts[1].endswith("Reply with valid JSON only."))
l = FakeLLM("not json", {"answer": 1})
a = answer_question("q", FakeSearch(H), l, tok)
check("still wrong after the repeat: model_error, not a fake I don't know", a.reason == "model_error" and not a.answered and not a.ok and a.text == "")
l = FakeLLM(None)
a = answer_question("q", FakeSearch(H), l, tok)
check("model error from the client", a.reason == "model_error" and a.error == "boom")
a = answer_question("q", FakeSearch([chunk(0, "w " * 50)]), FakeLLM(good), tok, budget=10)
check("nothing fits the budget: no model call", a.reason == "no_hits")

print("\n%d failed" % len(FAILED) if FAILED else "\nall ok")
sys.exit(1 if FAILED else 0)
