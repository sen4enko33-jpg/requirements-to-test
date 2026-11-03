"""Small text helpers shared by the extractors."""
import re


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def join_lines(lines: list[str]) -> str:
    """Join wrapped lines into one paragraph; 'require-' + 'ments' becomes 'requirements'."""
    out = ""
    for line in (collapse_ws(x) for x in lines):
        if not line:
            continue
        if not out:
            out = line
        elif re.search(r"[A-Za-z]-$", out) and line[0].islower():
            out = out[:-1] + line
        else:
            out += " " + line
    return out


def md_table(rows: list[list[str]]) -> list[str]:
    """Markdown table lines '| a | b |' with a separator after the first row."""
    rows = [[collapse_ws(c).replace("|", "/") for c in r] for r in rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(r) + " |" for r in rows]
    lines.insert(1, "|" + "---|" * width)
    return lines
