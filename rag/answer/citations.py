"""Checks of the model's citations by code (no model): references must exist, every fact sentence needs one."""
import re

IDK = "I don't know: the provided documents do not answer this question."
CITE = re.compile(r"\[(\d+)\]")


def cited_numbers(text: str) -> list[int]:
    """Numbers of the references in the text, in order of appearance, without repeats."""
    out = []
    for m in CITE.finditer(text):
        n = int(m.group(1))
        if n not in out:
            out.append(n)
    return out


def is_idk(text: str) -> bool:
    return text.strip().lower().startswith("i don't know")


def sentences(text: str) -> list[str]:
    """Sentences of the text. A reference written after the full stop ('... week. [1]') is moved in front of it, so it
    stays with its own sentence."""
    t = re.sub(r"([.!?])\s*((?:\[\d+\])+)", r"\2\1", text.strip())
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", t) if x.strip()]


def check(answer: str, sources: list[int], n_passages: int) -> dict:
    """{"cited": [...], "invalid": [...], "uncited_sentences": [...], "sources_mismatch": bool}.
    invalid: reference numbers that are not passages of the context (an invented source)."""
    cited = cited_numbers(answer)
    return {"cited": [n for n in cited if 1 <= n <= n_passages],
            "invalid": [n for n in cited if not 1 <= n <= n_passages],
            "uncited_sentences": [s for s in sentences(answer) if not CITE.search(s)],
            "sources_mismatch": set(sources) != set(cited)}
