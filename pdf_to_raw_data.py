import csv
import random
import re
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent
SRC_DIR = Path("/Users/v.senchenko/Downloads/req")
OUT_DIR = BASE_DIR / "data" / "texts"
INDEX_PATH = BASE_DIR / "data" / "index.csv"

SEED = 42
EXCERPTS_PER_DOC = 2
MIN_WORDS, MAX_WORDS = 300, 1500
TARGET_RANGE = (400, 900)   # target excerpt size is random within this range
MIN_ALPHA_RATIO = 0.6       # below this the chunk is likely a table / TOC / references
SKIP_HEAD_RATIO = 0.1       # skip the first 10% of chunks (title page, TOC)

SHALL_RE = re.compile(r"\bshall\b", re.IGNORECASE)

DOCS = {
    # formalized (shall density >= 8 per 1000 words)
    "2004 - grid bgc.pdf": "formalized",
    "2010 - home 1.3.pdf": "formalized",
    "1998 - themas.pdf": "formalized",
    "2003 - agentmom.pdf": "formalized",
    "2004 - sprat.pdf": "formalized",
    "2007 - ertms.pdf": "formalized",
    # mixed (1-8)
    "0000 - gamma j.pdf": "mixed",
    "2008 - caiso.pdf": "mixed",
    "2009 - library.pdf": "mixed",
    "2005 - grid 3D.pdf": "mixed",
    "2005 - znix.pdf": "mixed",
    # free-form (~0)
    "2001 - space fractions.pdf": "free",
    "2009 - video search.pdf": "free",
    "2007 - central trading system.pdf": "free",
    "2009 - gaia.pdf": "free",
    "2009 - peazip.pdf": "free",
}


def make_doc_id(filename):
    stem = Path(filename).stem.lower()
    return re.sub(r"[^a-z0-9]+", "_", stem).strip("_")


def extract_text(pdf_path):
    result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],  # "-" means write to stdout
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def split_paragraphs(text):
    parts = re.split(r"\n\s*\n", text)
    return [" ".join(p.split()) for p in parts if p.strip()]


def build_chunks(paragraphs, target_words):
    chunks, current, count = [], [], 0
    for p in paragraphs:
        current.append(p)
        count += len(p.split())
        if count >= target_words:
            chunks.append("\n\n".join(current))
            current, count = [], 0
    return chunks  # the incomplete tail is dropped


def is_good(chunk, group):
    words = len(chunk.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        return False
    alpha_ratio = sum(ch.isalpha() for ch in chunk) / len(chunk)
    if alpha_ratio < MIN_ALPHA_RATIO:
        return False
    if group == "formalized" and not SHALL_RE.search(chunk):
        return False
    return True


def pick_excerpts(text, group, n=EXCERPTS_PER_DOC):
    total_words = len(text.split())
    target = min(random.randint(*TARGET_RANGE), max(MIN_WORDS, total_words // 4))
    chunks = build_chunks(split_paragraphs(text), target)
    skip = int(len(chunks) * SKIP_HEAD_RATIO)
    mid = len(chunks) // 2

    candidates = [(i, c) for i, c in enumerate(chunks) if i >= skip and is_good(c, group)]
    first_half = [c for i, c in candidates if i < mid]
    second_half = [c for i, c in candidates if i >= mid]

    picks = [random.choice(half) for half in (first_half, second_half) if half]

    # fallback: one half had no good chunks, fill from whatever is left
    rest = [c for _, c in candidates if c not in picks]
    while len(picks) < n and rest:
        c = random.choice(rest)
        rest.remove(c)
        picks.append(c)
    return picks[:n]

def diagnose(text, group):
    paragraphs = split_paragraphs(text)
    chunks = build_chunks(paragraphs, 600)
    return {
        "words": len(text.split()),
        "paragraphs": len(paragraphs),
        "chunks": len(chunks),
        "size_ok": sum(MIN_WORDS <= len(c.split()) <= MAX_WORDS for c in chunks),
        "alpha_ok": sum(sum(ch.isalpha() for ch in c) / len(c) >= MIN_ALPHA_RATIO for c in chunks),
        "has_shall": sum(bool(SHALL_RE.search(c)) for c in chunks),
    }


def main():
    random.seed(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []

    for filename, group in DOCS.items():
        doc_id = make_doc_id(filename)
        try:
            text = extract_text(SRC_DIR / filename)
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            print(f"[ERROR] {filename}: {e}")
            continue

        excerpts = pick_excerpts(text, group)
        if len(excerpts) < EXCERPTS_PER_DOC:
            print(f"[WARN] {filename}: only {len(excerpts)} excerpt(s) found")

        for n, excerpt in enumerate(excerpts, start=1):
            (OUT_DIR / f"{doc_id}_{n}.txt").write_text(excerpt, encoding="utf-8")
            rows.append([f"{doc_id}_{n}", filename, group, n, len(excerpt.split())])

    with INDEX_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text_id", "source_file", "group", "excerpt_n", "word_count"])
        writer.writerows(rows)

    print(f"Done: {len(rows)} excerpts -> {OUT_DIR}")


if __name__ == "__main__":
    main()