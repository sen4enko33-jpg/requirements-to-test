"""One entry point for all formats."""
from pathlib import Path

from .extract_docx import extract_docx
from .extract_html import extract_html
from .extract_pdf import extract_pdf

EXTRACTORS = {".pdf": extract_pdf, ".doc": extract_docx, ".docx": extract_docx, ".rtf": extract_docx,
              ".html": extract_html, ".htm": extract_html}


def extract(path) -> tuple[str, dict]:
    """Markdown text and a small stats dict for one source file."""
    return EXTRACTORS[Path(path).suffix.lower()](path)
