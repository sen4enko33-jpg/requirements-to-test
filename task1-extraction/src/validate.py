"""Validation of a model answer against the schema, and the prompt for the one repair attempt."""
import collections
import difflib
import re

from pydantic import BaseModel, ValidationError

MAX_ERRORS_SHOWN = 5      # more errors than this are summarised
MAX_ANSWER_CHARS = 4000   # a runaway answer is cut so the repair prompt fits the local context


def describe(e: ValidationError) -> str:
    """Short, readable list of what is wrong (path: message), one per line."""
    lines = []
    for err in e.errors()[:MAX_ERRORS_SHOWN]:
        path = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"- {path}: {err['msg']}")
    if e.error_count() > MAX_ERRORS_SHOWN:
        lines.append(f"- ... and {e.error_count() - MAX_ERRORS_SHOWN} more")
    return "\n".join(lines)


def validate(text: str, model: type[BaseModel]) -> tuple[dict | None, str | None]:
    """(data, None) if `text` is valid JSON matching the schema, else (None, error list)."""
    try:
        return model.model_validate_json(text).model_dump(mode="json"), None
    except ValidationError as e:
        return None, describe(e)


def repair_prompt(prompt: str, bad_answer: str, errors: str) -> str:
    """Original prompt + the invalid answer + the errors, asking for a corrected answer."""
    if len(bad_answer) > MAX_ANSWER_CHARS:
        bad_answer = bad_answer[:MAX_ANSWER_CHARS] + "\n[... cut]"
    return (f"{prompt}\n\n---\n"
            "Your previous answer did not pass validation.\n\n"
            f"Previous answer:\n{bad_answer}\n\n"
            f"Validation errors:\n{errors}\n\n"
            "Return the corrected JSON only. Fix the listed errors and change nothing else.")


COPY_MIN_COVERAGE = 0.95  # share of a requirement's words that must be found in the excerpt
COPY_MAX_GAP = 15         # excerpt words allowed between the found pieces (page header, numbering)

_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", "\u00a0": " "})
_BULLETS = re.compile(r"[•·▪●○◦■□►*]")
_INNER_HYPHEN = re.compile(r"(?<=\w)-(?=\w)")                  # Windows-compatible == Windowscompatible
_NUMBERING = re.compile(r"(?<!\w)(\(?\d+(\.\d+)*[.)]|\(?[a-z][.)])(?=\s)")   # 1.  2)  3.2.1.1  (a)
_PUNCTUATION = re.compile(r"[^\w\s]")


def normalize_for_copy(text: str) -> str:
    """Text reduced to what must survive copying: words only. Layout that the prompt allows to remove
    (bullets, list numbers, line-break hyphens, page-header punctuation, case) is ignored."""
    text = text.replace("\u00ad", "")
    text = re.sub(r"-\s*\n\s*", "", text)           # word hyphenated at a line break
    text = text.translate(_QUOTES)
    text = _BULLETS.sub(" ", text)
    text = _INNER_HYPHEN.sub("", text)
    text = _NUMBERING.sub(" ", text)
    text = _PUNCTUATION.sub(" ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def strip_running_headers(text: str, min_repeat: int = 3) -> str:
    """Excerpt without page headers and footers: bare page numbers, lone bullets, "Page 25" / "Page 2 of 9" lines and lines that
    repeat min_repeat or more times (a running header). The prompt lets the model drop them, so a copy that
    skips them is correct; removing them from the source keeps them out of the gap that check_copy measures."""
    def key(line):
        return re.sub(r"\d+", "#", line.strip().lower())    # "Page 25" and "Page 26" are the same line
    counts = collections.Counter(key(line) for line in text.split("\n") if line.strip())
    kept = []
    for line in text.split("\n"):
        k = key(line)
        if not k or k in ("#", "•") or re.fullmatch(r"page #( of #)?", k) or (len(k) > 2 and counts[k] >= min_repeat):
            continue
        kept.append(line)
    return "\n".join(kept)


def check_copy(extraction: dict, source: str) -> list[str]:
    """Error lines for requirements whose `text` is not copied from the excerpt; empty list = all copied.

    A requirement passes if its words occur in the excerpt as one run, or if at least COPY_MIN_COVERAGE
    of them are found and the found pieces lie within COPY_MAX_GAP excerpt words of each other.
    Page headers and footers are removed from the excerpt first (strip_running_headers).
    It does not detect two neighbouring statements merged into one: every word of such a text is real."""
    src_words = normalize_for_copy(strip_running_headers(source)).split(" ")
    padded = " " + " ".join(src_words) + " "
    errors = []
    for i, req in enumerate(extraction["requirements"]):
        words = normalize_for_copy(req["text"]).split(" ")
        if words == [""] or f" {' '.join(words)} " in padded:
            continue
        blocks = [b for b in difflib.SequenceMatcher(None, words, src_words, autojunk=False)
                  .get_matching_blocks() if b.size]
        found = {b.a + k for b in blocks for k in range(b.size)}
        coverage = len(found) / len(words)
        pieces = [b for b in blocks if b.size >= 2] or blocks      # single words match by accident
        gap = 0
        if pieces:
            first, last = min(pieces, key=lambda b: b.b), max(pieces, key=lambda b: b.b)
            inner = [b for b in pieces if first.b <= b.b <= last.b]
            gap = (last.b + last.size - first.b) - sum(b.size for b in inner)
        label = f'requirements.{i}.text ("{req["text"][:50]}...")'
        if coverage < COPY_MIN_COVERAGE:
            missing = list(dict.fromkeys(w for j, w in enumerate(words) if j not in found))[:6]
            errors.append(f"- {label}: not copied from the excerpt, {100 * (1 - coverage):.0f}% of its words "
                          f"are not in the text (e.g. {', '.join(repr(w) for w in missing)}); "
                          "copy the statement exactly as it is printed")
        elif gap > COPY_MAX_GAP:
            errors.append(f"- {label}: assembled from pieces of the excerpt that are far apart "
                          f"({gap} words lie between them); copy one continuous statement")
    return errors


def cap_lines(lines: list[str]) -> str:
    """Error lines for the repair prompt, at most MAX_ERRORS_SHOWN of them."""
    shown = lines[:MAX_ERRORS_SHOWN]
    if len(lines) > MAX_ERRORS_SHOWN:
        shown.append(f"- ... and {len(lines) - MAX_ERRORS_SHOWN} more")
    return "\n".join(shown)


def drop_repeats(extraction: dict) -> tuple[dict, int]:
    """Remove requirements whose words repeat an earlier requirement of the same answer (a model that loops
    prints the same statement again and again). Returns the extraction and how many were removed."""
    seen, keep = set(), []
    for r in extraction["requirements"]:
        key = normalize_for_copy(r["text"])
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        keep.append(r)
    removed = len(extraction["requirements"]) - len(keep)
    return ({**extraction, "requirements": keep} if removed else extraction), removed
