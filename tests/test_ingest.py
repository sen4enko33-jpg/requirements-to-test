"""Checks of the ingestion cleaning and of the OCR rule. Run: python tests/test_ingest.py
Needs pymupdf (requirements.txt); the OCR checks are skipped when Tesseract is not installed."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.ingest.clean import clean, doc_version          # noqa: E402
from rag.ingest.text_utils import join_lines              # noqa: E402

failed = []


def check(name: str, cond: bool):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        failed.append(name)


def pages(*bodies, header="ACME Corp - Internal 2026-01-15", footer=None):
    footer = footer or (lambda i: f"Page {i} of {len(bodies)}")
    out = []
    for i, body in enumerate(bodies, 1):
        out.append(f"<!-- page {i} -->\n\n{header}\n\n{body}\n\n{footer(i)}")
    return "\n\n".join(out)


# --- running headers, footers, page numbers
md = pages("## 1. Purpose\n\nFirst page text.", "## 2. Scope\n\nSecond page text.", "## 3. Review\n\nThird page text.")
text, st = clean(md, "pdf")
check("running header removed on every page", "ACME Corp" not in text and st["running_lines_removed"] >= 3)
check("footer 'Page N of M' removed", "Page 1 of 3" not in text and "Page 3 of 3" not in text)
check("body text and numbered headings kept", "First page text." in text and "## 2. Scope" in text and "## 3. Review" in text)
check("page markers kept for citations", text.count("<!-- page") == 3)

text, st = clean(pages("## 1. A\n\nAlpha text here.", "## 2. B\n\nBeta text here.", header="Header", footer=lambda i: str(i)), "pdf")
check("lone page numbers removed", "\n\n1\n\n" not in "\n\n" + text and st["page_numbers_removed"] == 2)

two = pages("## 1. A\n\nAlpha.", "## 2. B\n\nBeta.")
check("fewer than 3 pages: a repeated line is not treated as a header", "ACME Corp" in clean(two, "pdf")[0])

text, _ = clean(pages("Words with the version 2 inside.", "More words.", "Even more words."), "pdf")
check("'version 2' inside a sentence is not a page number", "version 2 inside" in text)

# --- hyphenation and paragraphs cut by a page break
check("hyphenated line break joined", join_lines(["which secur-", "ity rules"]) == "which security rules")
md = "<!-- page 1 -->\n\nThe laptop must use full disk\n\n<!-- page 2 -->\n\nencryption at all times.\n\nNext paragraph."
text, st = clean(md, "pdf")
check("paragraph cut by a page break is merged", "full disk encryption at all times." in text and st["paragraphs_merged"] == 1)
md = "<!-- page 1 -->\n\nThe first sentence ends here.\n\n<!-- page 2 -->\n\nthe next starts lower case."
check("no merge after a finished sentence", clean(md, "pdf")[1].get("paragraphs_merged", 0) == 0)
md = "<!-- page 1 -->\n\nThe text goes on\n\n<!-- page 2 -->\n\n## 2. New section\n\nBody."
check("no merge into a heading", "## 2. New section" in clean(md, "pdf")[0])

# --- table of contents (a real document has a lot of text after the contents)
FILLER = "\n\n" + "\n\n".join("Filler paragraph number %d with enough words to look like a real document." % i for i in range(30))
body = "## Table of Contents\n\n1. Introduction ........ 3\n\n2. Scope ........ 4\n\n## 1. Introduction\n\nReal introduction text." + FILLER
text, st = clean(body, "pdf")
check("table of contents removed, next section kept", "Scope ........" not in text and "Real introduction text." in text)
body = "## Contents\n\n- SCOPE\n\n- OVERVIEW\n\n## SCOPE\n\nReal text of the scope." + FILLER
text, _ = clean(body, "html")
check("HTML table of contents (list items) removed", "- OVERVIEW" not in text and "Real text of the scope." in text)
body = "## Contents\n\nThis paragraph is body text without a page number and must stay.\n\n## 1. Intro\n\nx"
check("a body paragraph after 'Contents' is not eaten", "must stay" in clean(body, "pdf")[0])
run = "\n\n".join(f"Chapter {i} ............ {i}" for i in range(1, 7))
check("run of dot-leader lines without a heading removed", "Chapter 3" not in clean("## Intro\n\n" + run + "\n\n## Next\n\ntext", "pdf")[0])

# --- unicode, navigation, leftovers
text, st = clean("## T\n\nNe�ios ﬁle re­quirement", "html")
check("U+FFFD and soft hyphen removed, ligature normalised", "�" not in text and "file requirement" in text and st["fffd_removed"] == 1)
nav = "| Home | Hosting | Domains | Support | Contacts |\n|---|---|---|---|---|"
check("HTML navigation table above the first heading removed", "Hosting" not in clean(nav + "\n\n## Title\n\nText.", "html")[0])
check("the same table is kept in a PDF", "Hosting" in clean(nav + "\n\n## Title\n\nText.", "pdf")[0])
check("a data table below a heading is kept", "Hosting" in clean("## Title\n\n" + nav, "html")[0])
text, st = clean("## T\n\n__________\n\nreal text\n\nx", "docx")
check("separator lines and single letters removed", "____" not in text and st["garbage_removed"] == 2)

# --- warnings
check("document without headings gets a warning", "no headings" in clean("just text " * 50, "docx")[1]["warnings"])
check("version and ISO date found on the first page", doc_version("Remote Work Policy\n\nEffective 2026-01-15\n\nVersion 2.1") == {"version": "2.1", "date": "2026-01-15"})
check("dates written with month names are converted", [doc_version(t)["date"] for t in ("Date: 18 March 2004", "August 7, 2009", "Galecia Group January 2009", "1st May, 2001")]
      == ["2004-03-18", "2009-08-07", "2009-01", "2001-05-01"])
check("no version or date gives None", doc_version("Just a title") == {"version": None, "date": None})

# --- OCR rule (needs pymupdf and Tesseract)
if shutil.which("tesseract"):
    import pymupdf
    from rag.ingest.extract_pdf import extract_pdf
    tmp = tempfile.mkdtemp()
    try:
        src = pymupdf.open()
        for i in range(2):
            pg = src.new_page()
            pg.insert_text((72, 90), "Remote Work Policy" if i == 0 else "Eligibility rules", fontsize=22)
            pg.insert_textbox(pymupdf.Rect(72, 130, 520, 400), "Employees may work remotely up to two days per week. " * 6, fontsize=12)
        text_pdf = os.path.join(tmp, "text.pdf"); src.save(text_pdf)
        scan = pymupdf.open()
        for pg in pymupdf.open(text_pdf):
            page = scan.new_page(width=pg.rect.width, height=pg.rect.height)
            page.insert_image(page.rect, pixmap=pg.get_pixmap(dpi=200))
        scan_pdf = os.path.join(tmp, "scan.pdf"); scan.save(scan_pdf)
        md, meta = extract_pdf(scan_pdf)
        check("scanned PDF is recognised with OCR (not skipped)", meta["ocr_pages"] == 2 and "work remotely" in md)
        check("OCR keeps the heading structure", "# Remote Work Policy" in md)
        fig = pymupdf.open()
        for i in range(2):
            page = fig.new_page()
            page.insert_textbox(pymupdf.Rect(72, 72, 520, 700), "Digital text of the document. " * 40, fontsize=11)
            page.insert_image(pymupdf.Rect(72, 720, 120, 760), pixmap=pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False))
        fig_pdf = os.path.join(tmp, "fig.pdf"); fig.save(fig_pdf)
        check("a digital PDF with a small picture is not OCR-ed", extract_pdf(fig_pdf)[1]["ocr_pages"] == 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
else:
    print("skip OCR checks: Tesseract is not installed")

print(f"\n{len(failed)} failed" if failed else "\nall checks passed")
sys.exit(1 if failed else 0)
