"""Structural quality metrics of a chunking (heuristics on the chunk text, the same for every strategy)."""
import re
import statistics

SENTENCE_END = ".!?:;)\"”'"


def last_line(text: str) -> str:
    return text.rstrip().split("\n")[-1].strip()


def starts_mid_sentence(text: str) -> bool:
    t = text.lstrip("-|* \n")
    return bool(re.match(r"[a-z]", t))


def ends_mid_sentence(text: str) -> bool:
    """The last line is a long run of words that does not end like a sentence (short lines are labels or headings)."""
    ln = last_line(text)
    return not ln.startswith(("|", "- ")) and len(ln.split()) >= 8 and ln[-1] not in SENTENCE_END


def metrics(chunks: list[dict], headings: set[str]) -> dict:
    n = len(chunks)
    sizes = [c["n_words"] for c in chunks] or [0]
    srt = sorted(sizes)
    pct = lambda k: round(100 * sum(1 for c in chunks if k(c)) / max(n, 1), 1)
    return {"chunks": n, "words_mean": round(statistics.mean(sizes)), "words_median": round(statistics.median(sizes)),
            "words_p95": srt[min(int(0.95 * len(srt)), len(srt) - 1)], "words_max": srt[-1],
            "start_mid_sentence_pct": pct(lambda c: starts_mid_sentence(c["text"])),
            "end_mid_sentence_pct": pct(lambda c: ends_mid_sentence(c["text"])),
            "spans_sections_pct": pct(lambda c: len(c["sections"]) > 1),
            "ends_with_heading_pct": pct(lambda c: last_line(c["text"]) in headings)}
