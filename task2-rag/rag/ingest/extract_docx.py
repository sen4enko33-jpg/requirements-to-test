"""DOC/DOCX/RTF -> Markdown. DOC and RTF are converted to DOCX with LibreOffice first.
Title -> '# ', 'Heading N' -> N+1 hashes, list paragraphs -> '- ' ('List Number' -> '1. '), tables -> '| a | b |' rows."""
import re
import subprocess
import tempfile
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from .text_utils import collapse_ws, md_table

NUMBERED = re.compile(r"^(\d+(?:\.\d+){0,4})\.?\s+[A-Z\"'(]")


def to_docx(path: Path, tmp: Path) -> Path:
    if path.suffix.lower() == ".docx":
        return path
    cmd = ["soffice", "-env:UserInstallation=file:///tmp/lo_profile_rag", "--headless",
           "--convert-to", "docx:MS Word 2007 XML", "--outdir", str(tmp), str(path)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    out = tmp / (path.stem + ".docx")
    if not out.exists():
        raise RuntimeError(f"LibreOffice produced no DOCX for {path.name}")
    return out


def _is_list(p: Paragraph, style: str) -> bool:
    return style.startswith("List") or p._p.pPr is not None and p._p.pPr.numPr is not None


def extract_docx(path) -> tuple[str, dict]:
    path = Path(path)
    with tempfile.TemporaryDirectory() as tmp:
        doc = Document(str(to_docx(path, Path(tmp))))
        out, n_head, n_list, n_tab, counter = [], 0, 0, 0, 0
        for child in doc.element.body.iterchildren():
            if child.tag.endswith("}tbl"):
                table, rows = Table(child, doc), []
                for r in table.rows:
                    cells, prev = [], None
                    for c in r.cells:
                        if prev is not None and c._tc is prev:
                            continue                      # merged cell appears once
                        prev = c._tc
                        cells.append(c.text)
                    rows.append(cells)
                lines = md_table(rows)
                if lines:
                    out.append("\n".join(lines))
                    n_tab += 1
                counter = 0
                continue
            if not child.tag.endswith("}p"):
                continue
            p = Paragraph(child, doc)
            text = collapse_ws(p.text)
            if not text:
                continue
            style = p.style.name if p.style is not None else ""
            m = re.fullmatch(r"Heading (\d)", style)
            if style == "Title":
                out.append("# " + text); n_head += 1; counter = 0
            elif m:
                out.append("#" * min(int(m.group(1)) + 1, 6) + " " + text); n_head += 1; counter = 0
            elif style.startswith("List Number"):
                counter += 1
                out.append(f"{counter}. {text}"); n_list += 1
            elif _is_list(p, style):
                out.append("- " + text); n_list += 1; counter = 0
            else:
                counter = 0
                runs = [r for r in p.runs if r.text.strip()]
                bold = bool(runs) and all(r.bold for r in runs)
                nm = NUMBERED.match(text)
                if nm and bold and len(text) <= 90 and not text.endswith("."):     # DOCs without real heading styles
                    out.append("#" * min(nm.group(1).count(".") + 2, 6) + " " + text); n_head += 1
                else:
                    out.append(text)
    meta = {"headings": n_head, "list_items": n_list, "tables": n_tab}
    return "\n\n".join(out), meta
