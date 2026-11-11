"""Tokens for BM25 and the metadata filter shared by all search modes."""
import re

STOP = frozenset("a an and are as at be by for from has have in is it its of on or that the this to was were will with".split())
TOKEN = re.compile(r"[a-z0-9]+(?:[._/-][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    """Lower-case words and identifiers (`req-12`, `i86obj.c` stay one token); English stop words are dropped."""
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP]


def matches(meta: dict, filters: dict | None) -> bool:
    """A filter is {field: value} or {field: [values]}; every field must match (a list matches any of its values)."""
    for key, want in (filters or {}).items():
        have = meta.get(key)
        ok = have in want if isinstance(want, (list, tuple, set, frozenset)) else have == want
        if not ok:
            return False
    return True
