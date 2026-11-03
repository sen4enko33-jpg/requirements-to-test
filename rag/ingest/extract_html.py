"""HTML -> Markdown: take <main> (else <body>), h1-h6 -> '# '..'###### ', li -> '- ', table rows -> '| a | b |'."""
import re

from bs4 import BeautifulSoup

from .text_utils import collapse_ws, md_table

DROP = ["script", "style", "noscript", "nav", "footer", "aside", "form", "iframe"]
HEADINGS = {f"h{i}": i for i in range(1, 7)}


def _read(path) -> str:
    raw = open(path, "rb").read()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_html(path) -> tuple[str, dict]:
    soup = BeautifulSoup(_read(path), "lxml")
    root = soup.find("main") or soup.body or soup
    for t in root.find_all(DROP):
        t.decompose()
    title = collapse_ws(soup.title.get_text()) if soup.title else ""
    out, n_head, n_list, n_tab = [], 0, 0, 0
    handled = set()
    has_h = bool(root.find(list(HEADINGS)))
    numbered = re.compile(r"^(\d+(?:\.\d+){0,4})\.?\s+\S")
    for el in root.find_all(list(HEADINGS) + ["p", "li", "table", "pre", "blockquote"]):
        if id(el) in handled:
            continue
        if el.name == "table":
            if el.find(["table", "ul", "ol"] + list(HEADINGS)):
                continue                       # a layout table: its content is processed element by element
            rows = [[c.get_text(" ") for c in tr.find_all(["td", "th"], recursive=False)]
                    for tr in el.find_all("tr") if tr.find_parent("table") is el]
            lines = md_table(rows)
            if lines:
                out.append("\n".join(lines))
                n_tab += 1
            for d in el.find_all(True):
                handled.add(id(d))
            continue
        if el.name in ("p", "blockquote", "pre") and el.find_parent("li"):
            continue
        text = collapse_ws(el.get_text(" "))
        if not text:
            continue
        bold_len = sum(len(collapse_ws(b.get_text(" "))) for b in el.find_all(["b", "strong"]))
        fallback = (not has_h and el.name in ("p", "li") and len(text) <= 90
                    and not text.endswith((".", ",", ";", ":")) and bold_len >= 0.9 * len(text)
                    and re.search(r"[A-Za-z]", text) and not el.find("a", href=True))   # links = table of contents entries
        if el.name in HEADINGS:
            out.append("#" * HEADINGS[el.name] + " " + text)
            n_head += 1
        elif fallback:                      # old (Word-exported) pages: a short all-bold paragraph or list item is a heading
            m = numbered.match(text)
            if m:
                level = m.group(1).count(".") + 2
            elif el.name == "li":
                level = 1 + len(el.find_parents(["ol", "ul"]))
            else:
                level = 2
            out.append("#" * min(level, 5) + " " + text)
            n_head += 1
        elif el.name == "li":
            nested = el.find(["ul", "ol"])
            own = " ".join(t for t in el.find_all(string=True) if not nested or nested not in t.parents)
            out.append("- " + collapse_ws(own))
            n_list += 1
        else:
            out.append(text)
    if not n_head and title:
        out.insert(0, "# " + title)       # old pages without <h1>: the page title is the best heading we have
    meta = {"title": title, "headings": n_head, "list_items": n_list, "tables": n_tab, "used_main": bool(soup.find("main"))}
    return "\n\n".join(out), meta
