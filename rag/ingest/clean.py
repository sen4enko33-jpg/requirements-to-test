"""Cleaning of the Markdown produced by the extractors.

Every rule counts what it removed (the numbers go to the manifest) and the order matters: Unicode, running headers and
page numbers, tables of contents, HTML navigation, paragraphs split by a page break, leftovers.
"""
import math
import re
import unicodedata
from collections import Counter

from .text_utils import join_lines

PAGE_MARK = re.compile(r"^<!-- page (\d+) -->$")
# '12', 'iv', 'Page 3 of 40', '- 7 -' (roman numerals only up to 39: 'mix' or 'mild' are words)
PAGE_NUM = re.compile(r"^[\W_]*(?:page\s*)?(?:\d{1,4}|(?=[xvil])(?:xl|l?x{0,3})(?:ix|iv|v?i{0,3}))"
                      r"(?:\s*(?:of|/)\s*\d{1,4})?[\W_]*$", re.I)
TOC_HEADING = re.compile(r"^#{1,6}\s*(table of contents|contents|list of figures|list of tables)\s*$", re.I)
TOC_TAIL = re.compile(r"(?:\.{3,}|\s)\s*(?:\d{1,4}|[ivxl]{1,5})$", re.I)
DOT_LEADER = re.compile(r"\.{4,}\s*\d{1,4}$")
SENTENCE_END = re.compile(r"[.!?:;)\]\"”']$")
MAX_REMOVED_SHARE = 0.25          # more than this share of the words removed = a warning
MAX_TOC_SHARE = 0.20              # a table of contents longer than this share of the text is not removed


def _normalize(text: str) -> tuple[str, int, int]:
    text = unicodedata.normalize("NFKC", text)
    n_fffd, n_shy = text.count("\ufffd"), text.count("\u00ad")
    text = text.replace("\ufffd", "").replace("\u00ad", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text, n_fffd, n_shy


def _is_heading(u: str) -> bool:
    return u.startswith("#")


def _is_plain(u: str) -> bool:
    return not (u.startswith(("#", "|", "- ", "<!--")) or re.match(r"^\d+\. ", u))


def _key(unit: str) -> str:
    """Comparison key of a possible running header or footer: digits -> '#', no spaces, lower case."""
    if unit.startswith("|") or PAGE_MARK.match(unit):
        return ""
    t = re.sub(r"^(#+\s*|-\s+)", "", unit).strip()
    if not t or len(t) > 150 or re.match(r"^\d+(?:\.\d+)*\.?\s+\D", t):      # numbered headings are unique sections
        return ""
    return re.sub(r"\s+", "", re.sub(r"\d", "#", t.lower()))


def _edge_idx(n: int) -> set[int]:
    return set(range(min(2, n))) | set(range(max(n - 2, 0), n))


def _remove_running(pages: list[list], stats: Counter) -> list[list]:
    """Drop lines that repeat at the top or bottom of at least 30% of the pages (min. 3) and lone page numbers."""
    if not any(p[0] for p in pages):
        return pages                                           # no page markers: not a paginated document
    counts = Counter()
    running: set[str] = set()
    if len(pages) >= 3:                                        # a repeated line needs enough pages to be a header
        for _, us in pages:
            counts.update({k for i in _edge_idx(len(us)) if (k := _key(us[i]))})
        need = max(3, math.ceil(0.3 * len(pages)))
        running = {k for k, c in counts.items() if c >= need}
    seen = []
    out = []
    for marker, us in pages:
        keep = []
        edges = _edge_idx(len(us))
        for i, u in enumerate(us):
            if i in edges and _key(u) in running and _key(u):
                stats["running_lines_removed"] += 1
                if u not in seen and len(seen) < 6:
                    seen.append(u)
                continue
            if i in edges and PAGE_NUM.match(u) and _is_plain(u):
                stats["page_numbers_removed"] += 1
                continue
            keep.append(u)
        out.append([marker, keep])
    stats["running_examples"] = seen
    return out


def _toc_like(u: str) -> bool:
    t = re.sub(r"^(#+\s*|-\s+)", "", u).strip()
    return len(t) <= 160 and bool(TOC_TAIL.search(t))


DOT_LEADER_LINE = re.compile(r"(?:\.\s?){5,}")


def _remove_leader_lines(units: list[str], stats: Counter) -> list[str]:
    """Lines with dot leaders ('Introduction ......... 3') are left-overs of a table of contents: drop them."""
    out, n = [], 0
    for u in units:
        if u.startswith(("<!--", "|")) or not DOT_LEADER_LINE.search(u):
            out.append(u)
            continue
        keep = [ln for ln in u.split("\n") if not DOT_LEADER_LINE.search(ln)]
        n += len(u.split("\n")) - len(keep)
        if keep:
            out.append("\n".join(keep))
    stats["dot_leader_lines_removed"] = n
    return out


def _remove_toc(units: list[str], stats: Counter) -> list[str]:
    total = sum(len(u) for u in units) or 1
    drop: set[int] = set()
    for h, u in enumerate(units):
        if not TOC_HEADING.match(u):
            continue
        level = len(u) - len(u.lstrip("#"))
        region = {h}
        for j in range(h + 1, len(units)):
            v = units[j]
            if PAGE_MARK.match(v):
                continue
            if _is_heading(v):
                if _toc_like(v):
                    region.add(j); continue
                break
            if v.startswith("- ") and len(v) <= 120 or _toc_like(v):
                region.add(j); continue
            break
        if sum(len(units[k]) for k in region) > MAX_TOC_SHARE * total:
            stats["warnings"] = stats.get("warnings", []) + [f"table of contents at unit {h} not removed: too long"]
            continue
        drop |= region
    # a run of >= 5 lines with dot leaders and page numbers without a heading above it
    run = []
    for j, u in enumerate(units + [""]):
        if DOT_LEADER.search(u):
            run.append(j)
            continue
        if PAGE_MARK.match(u):
            continue
        if len(run) >= 5:
            drop |= set(run)
        run = []
    stats["toc_units_removed"] = len(drop)
    return [u for j, u in enumerate(units) if j not in drop]


def _remove_nav_tables(units: list[str], stats: Counter) -> list[str]:
    """HTML: a short table of single words above the first heading is the site navigation bar."""
    out, seen_heading = [], False
    for u in units:
        if _is_heading(u):
            seen_heading = True
        if not seen_heading and u.startswith("|"):
            rows = [ln for ln in u.split("\n") if not re.fullmatch(r"\|(?:-+\|)+", ln)]
            cells = [c.strip() for ln in rows for c in ln.strip("|").split("|")]
            if len(rows) <= 2 and len(cells) >= 4 and max(len(c) for c in cells) <= 25:
                stats["nav_tables_removed"] += 1
                continue
        out.append(u)
    return out


def _merge_across_pages(units: list[str], stats: Counter) -> list[str]:
    """A paragraph cut by a page break continues on the next page: join it (the page marker stays before the rest)."""
    out: list[str] = []
    last_text = None                 # index in out of the last non-marker unit
    pending = False                  # a page marker came after that unit
    for u in units:
        if PAGE_MARK.match(u):
            out.append(u)
            pending = last_text is not None
            continue
        if (pending and last_text is not None and _is_plain(u) and u[:1].islower()
                and _is_plain(out[last_text]) and not SENTENCE_END.search(out[last_text])):
            out[last_text] = join_lines([out[last_text], u])
            stats["paragraphs_merged"] += 1
            pending = False
            continue
        out.append(u)
        last_text, pending = len(out) - 1, False
    return out


def clean(md: str, fmt: str) -> tuple[str, dict]:
    """Cleaned Markdown and the statistics of the cleaning. fmt is the source format ('pdf', 'doc', 'html', ...)."""
    stats: Counter = Counter()
    words_before = len(md.split())
    md, stats["fffd_removed"], stats["soft_hyphens_removed"] = _normalize(md)
    units = [u.strip() for u in re.split(r"\n{2,}", md) if u.strip()]

    pages: list[list] = [[None, []]]
    for u in units:
        if PAGE_MARK.match(u):
            pages.append([u, []])
        else:
            pages[-1][1].append(u)
    pages = [p for p in pages if p[0] or p[1]]
    pages = _remove_running(pages, stats)
    flat = [x for marker, us in pages for x in ([marker] if marker else []) + us]

    flat = _remove_toc(flat, stats)
    flat = _remove_leader_lines(flat, stats)
    if fmt in ("html", "htm"):
        flat = _remove_nav_tables(flat, stats)
    flat = _merge_across_pages(flat, stats)
    before = len(flat)
    flat = [u for u in flat if not (re.fullmatch(r"[\W_]{3,}", u) and not u.startswith(("|", "<!--")))
            and not re.fullmatch(r"[A-Za-z]", u)]
    stats["garbage_removed"] = before - len(flat)

    text = "\n\n".join(flat).strip() + "\n"
    words_after = len(re.sub(r"<!--.*?-->", "", text).split())
    stats["words_before"], stats["words_after"] = words_before, words_after
    stats["removed_share"] = round(1 - words_after / max(words_before, 1), 3)
    warnings = list(stats.pop("warnings", []))
    if stats["removed_share"] > MAX_REMOVED_SHARE:
        warnings.append(f"cleaning removed {stats['removed_share']:.0%} of the words")
    if words_after < 300:
        warnings.append(f"very short document ({words_after} words)")
    if not any(_is_heading(u) for u in flat):
        warnings.append("no headings")
    stats["warnings"] = warnings
    return text, dict(stats)


MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                        "september", "october", "november", "december"], 1)}
_MONTH = "|".join(MONTHS)
DATE_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH}),?\s+(\d{{4}})\b", re.I)
DATE_MDY = re.compile(rf"\b({_MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
DATE_MY = re.compile(rf"\b({_MONTH})\s+(\d{{4}})\b", re.I)


def _find_date(head: str) -> str | None:
    """First date of the title page as ISO ('2004-03-18', or '2009-01' when only month and year are given)."""
    iso = re.search(r"\b(?:effective|date[d]?|revised|released)\b[^\n\d]{0,12}(\d{4}-\d{2}-\d{2})", head, re.I) \
        or re.search(r"\b(\d{4}-\d{2}-\d{2})\b", head)
    if iso:
        return iso.group(1)
    found = []
    for rx, order in ((DATE_DMY, "dmy"), (DATE_MDY, "mdy"), (DATE_MY, "my")):
        m = rx.search(head)
        if m:
            g = m.groups()
            day, mon, year = (g[0], g[1], g[2]) if order == "dmy" else (g[1], g[0], g[2]) if order == "mdy" else (None, g[0], g[1])
            iso_d = f"{int(year):04d}-{MONTHS[mon.lower()]:02d}" + (f"-{int(day):02d}" if day else "")
            found.append((m.start(), iso_d))
    return min(found)[1] if found else None


def doc_version(raw_md: str) -> dict:
    """Version and date from the first page, before the running headers are removed (best effort, may be None)."""
    head = raw_md[:4000]
    ver = re.search(r"\b(?:version|ver\.?|rev(?:ision)?)\s*[:.]?\s*v?(\d+(?:\.\d+){0,3})", head, re.I)
    return {"version": ver.group(1) if ver else None, "date": _find_date(head)}
