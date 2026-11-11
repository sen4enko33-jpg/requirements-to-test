"""PDF -> Markdown (PyMuPDF). Headings come from font size, bold and section numbers; bullets become '- ' lines.

A page marker '<!-- page N -->' is written before each page (used by the cleaning step, then removed or kept as metadata).
Tables are not parsed: their text stays in reading order.
"""
import glob
import os
import re
from collections import Counter

import pymupdf

from .text_utils import collapse_ws, join_lines

MIN_CHARS_PER_PAGE = 300          # below this average (after OCR of scanned pages) the document is rejected
NUMBERED = re.compile(r"^(\d+(?:\.\d+){0,4})\.?\s+[A-Z\"'(]")
BULLET = re.compile(r"^\s*[•·▪◦●■–\-\*]\s+(?=\S)")


OCR_MIN_CHARS = 80                # a scan page has fewer text-layer characters than this
OCR_MIN_IMAGE_SHARE = 0.6          # a picture covering at least this share of the page makes it a scan page
OCR_MIN_PAGE_SHARE = 0.5           # OCR only when at least this share of the pages are scan pages
OCR_DPI = 300
OCR_LANG = os.environ.get("RAG_OCR_LANG", "eng")   # Tesseract language pack(s), e.g. "eng+ukr"


class ScannedPdfError(Exception):
    """The PDF has no usable text, not even after OCR (OCR missing or the scan is unreadable)."""


def _tessdata():
    env = os.environ.get("TESSDATA_PREFIX")
    if env and os.path.isdir(env):
        return env
    for pat in ("/usr/share/tesseract-ocr/*/tessdata", "/usr/share/tessdata", "/opt/homebrew/share/tessdata",
                "/usr/local/share/tessdata"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def _blocks(page, tp=None):
    for b in page.get_text("dict", textpage=tp)["blocks"]:
        if b["type"] != 0:
            continue
        lines = []
        for ln in b["lines"]:
            spans = [s for s in ln["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = collapse_ws("".join(s["text"] for s in ln["spans"]))
            size = round(max(spans, key=lambda s: len(s["text"]))["size"], 1)
            bold = all((s["flags"] & 16) or "bold" in s["font"].lower() for s in spans)
            lines.append((text, size, bold))
        if lines:
            yield lines


def _units(page, tp=None):
    """Blocks cut into runs of lines with the same size and weight (a heading line and its paragraph are separate units)."""
    for bl in _blocks(page, tp):
        run = [bl[0]]
        for ln in bl[1:]:
            if abs(ln[1] - run[-1][1]) <= 0.4 and ln[2] == run[-1][2]:
                run.append(ln)
            else:
                yield run
                run = [ln]
        yield run


def extract_pdf(path) -> tuple[str, dict]:
    doc = pymupdf.open(path)
    # A scan is a document whose pages are mostly one big picture with (almost) no text layer. Pages with a figure and
    # little text in an otherwise digital PDF are not scans: OCR of a diagram only produces noise.
    def _scanned(page):
        if len(page.get_text().strip()) >= OCR_MIN_CHARS:
            return False
        area = page.rect.width * page.rect.height
        return any(pymupdf.Rect(im["bbox"]).get_area() >= OCR_MIN_IMAGE_SHARE * area for im in page.get_image_info())

    flags = [_scanned(p) for p in doc]
    do_ocr = sum(flags) >= OCR_MIN_PAGE_SHARE * max(len(flags), 1)
    pages, ocr_pages = [], []
    for i, page in enumerate(doc, 1):
        if do_ocr and flags[i - 1]:
            try:
                tp = page.get_textpage_ocr(language=OCR_LANG, dpi=OCR_DPI, full=True, tessdata=_tessdata())
            except Exception as e:                                                  # Tesseract or language pack missing
                raise ScannedPdfError(f"page {i} needs OCR but it failed: {e}") from e
            pages.append(list(_units(page, tp)))
            ocr_pages.append(i)
        else:
            pages.append(list(_units(page)))
    n_chars = sum(len(t) for pg in pages for bl in pg for t, _, _ in bl)
    per_page = n_chars / max(len(pages), 1)
    if per_page < MIN_CHARS_PER_PAGE:
        raise ScannedPdfError(f"{per_page:.0f} characters per page (< {MIN_CHARS_PER_PAGE}) even after OCR of {len(ocr_pages)} pages")

    sizes = Counter()
    for pg in pages:
        for bl in pg:
            for t, s, _ in bl:
                sizes[s] += len(t)
    body = sizes.most_common(1)[0][0]

    def heading_kind(bl):
        """(is_heading, numbered_depth or None, size) for a block of at most two short lines."""
        if len(bl) > 2:
            return False, None, 0
        text = join_lines([t for t, _, _ in bl])
        size = max(s for _, s, _ in bl)
        bold = all(b for _, _, b in bl)
        if not text or len(text) > 110 or text.endswith((".", ",", ";", ":")) or re.fullmatch(r"[\d\W]+", text):
            return False, None, size
        m = NUMBERED.match(text)
        if m and len(text) <= 90 and (bold or size > body + 0.4 or len(bl) == 1) \
                and not re.search(r"\b(shall|must|will|should)\b", text):
            return True, m.group(1).count(".") + 1, size
        if size >= body * 1.15:            # bold alone at body size is not a heading (requirement ids, labels)
            return True, None, size
        return False, None, size

    # rank unnumbered heading sizes (largest = highest level); the largest on page 1 is the title
    cand = [heading_kind(bl) for bl in pages[0]]
    all_cand = [heading_kind(bl) for pg in pages for bl in pg]
    sizes_h = sorted({s for ok, d, s in all_cand if ok and d is None and s > body + 0.4}, reverse=True)
    page1 = [s for ok, d, s in cand if ok and d is None and s >= body * 1.4]
    title_size = max(page1) if page1 else None
    title_done, last_title_idx = False, None

    out, n_head, n_list, last_plain = [], 0, 0, None   # last_plain: index of an OCR paragraph that may continue
    for i, pg in enumerate(pages, 1):
        out.append(f"<!-- page {i} -->")
        last_plain = None
        for bl in pg:
            ok, depth, size = heading_kind(bl)
            if ok:
                text = join_lines([t for t, _, _ in bl])
                if depth is not None:
                    level = min(depth + 1, 5)
                elif title_size and size == title_size and i == 1 and (not title_done or last_title_idx == len(out) - 1):
                    if title_done:                      # a title that continues on the next line
                        out[-1] += " " + text
                        continue
                    level, title_done = 1, True
                    last_title_idx = len(out)
                else:
                    ranks = [s for s in sizes_h if not (title_size and s == title_size)]
                    level = 2 + (ranks.index(size) if size in ranks else len(ranks))
                    level = min(level, 5)
                out.append("#" * level + " " + text)
                last_plain = None
                n_head += 1
                continue
            items, cur = [], None            # paragraph text and list items of the block
            for t, _, _ in bl:
                if BULLET.match(t):
                    cur = ["- " + BULLET.sub("", t)]
                    items.append(cur)
                    n_list += 1
                elif cur is not None and cur[0].startswith("- "):
                    cur.append(t)
                else:
                    if cur is None or cur[0].startswith("- "):
                        cur = []
                        items.append(cur)
                    cur.append(t)
            for it in items:
                is_bullet = it[0].startswith("- ")
                line = ("- " if is_bullet else "") + join_lines([it[0][2:] if is_bullet else it[0]] + it[1:])
                if i in ocr_pages and not is_bullet and last_plain == len(out) - 1:
                    out[-1] = join_lines([out[-1], line])       # OCR returns one block per line: rebuild the paragraph
                    continue
                out.append(line)
                last_plain = len(out) - 1 if (i in ocr_pages and not is_bullet) else None
    meta = {"pages": len(pages), "chars_per_page": round(per_page), "headings": n_head, "list_items": n_list,
            "ocr_pages": len(ocr_pages), **({"ocr_lang": OCR_LANG} if ocr_pages else {})}
    return "\n\n".join(out), meta
