"""Deterministic scorers for the answer test set (rag/eval/testset.jsonl). Pure functions: no model, no network.

A question passes when every check that applies to it passes:
  refusal     answerable/trap: the system answered; unanswerable: it said "I don't know" (anywhere in the answer) and cited nothing
  source      answerable/trap: at least one cited document is an expected source
  key_facts   every group of key facts has at least one alternative in the answer (case-insensitive substring)
  forbidden   trap with forbidden_sources: none of them is cited
  current     trap with stale_facts: the key fact stands before any stale value (the newest version is not put second)
  citations   no invented reference number
"""
import re

_NUM = re.compile(r"\d")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().replace(" ", " ")).strip()


def _find(text: str, needle: str) -> int:
    """Position of needle in text, -1 when absent. A needle that is only digits must not sit inside a longer number
    ("40" is not found in "400" or "2040"), otherwise a wrong number could pass."""
    n = norm(needle)
    if not n:
        return -1
    if n.replace(".", "").replace(",", "").isdigit():
        m = re.search(rf"(?<![\d.,]\d)(?<!\d){re.escape(n)}(?!\d)(?![.,]\d)", text)
        return m.start() if m else -1
    return text.find(n)


def facts_found(text: str, groups: list[list[str]]) -> list[bool]:
    t = norm(text)
    return [any(_find(t, alt) >= 0 for alt in g) for g in groups]


def score(q: dict, a: dict) -> dict:
    """q: a test-set question; a: {answered, text, citations:[{doc_id}], problems}. Returns every check and the verdict."""
    cited = {c["doc_id"] for c in a.get("citations", [])}
    out = {}
    if q["must_refuse"]:
        refused = (not a["answered"]) or "i don't know" in norm(a["text"]).replace("\u2019", "'")      # also "... Therefore, I don't know: ..."
        out["refusal"] = refused and not cited
    else:
        out["refusal"] = bool(a["answered"])
        if a["answered"]:
            out["source"] = bool(cited & set(q["expected_sources"]))
            out["key_facts"] = all(facts_found(a["text"], q["key_facts"]))
            if q.get("forbidden_sources"):
                out["forbidden"] = not (cited & set(q["forbidden_sources"]))
            if q.get("stale_facts"):
                t = norm(a["text"])
                first_good = min([p for g in q["key_facts"] for alt in g if (p := _find(t, alt)) >= 0], default=-1)
                stale = [p for s in q["stale_facts"] if (p := _find(t, s)) >= 0 and p != first_good]
                out["current"] = first_good >= 0 and all(first_good < p for p in stale)
        else:
            out.update(source=False, key_facts=False)
    out["citations"] = "invalid_reference" not in a.get("problems", [])
    out["pass"] = all(out.values())
    return out


def summarize(rows: list[dict]) -> dict:
    """rows: [{category, scores}]. Pass rates per category plus the metrics that the report shows."""
    def rate(sel, key):
        sel = [r for r in rows if sel(r) and key in r["scores"]]
        return round(sum(r["scores"][key] for r in sel) / len(sel), 3) if sel else None
    cat = lambda c: (lambda r: r["category"] == c)
    answ = lambda r: r["category"] != "unanswerable"
    return {
        "n": len(rows),
        "pass_all": rate(lambda r: True, "pass"),
        "pass_answerable": rate(cat("answerable"), "pass"),
        "pass_trap": rate(cat("trap"), "pass"),
        "pass_unanswerable": rate(cat("unanswerable"), "pass"),
        "source_cited": rate(answ, "source"),
        "key_facts": rate(answ, "key_facts"),
        "answered_when_answerable": rate(answ, "refusal"),     # recall of answering
        "refused_when_unanswerable": rate(cat("unanswerable"), "refusal"),
        "citations_valid": rate(lambda r: True, "citations"),
    }
