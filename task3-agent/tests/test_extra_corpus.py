"""Checks of the extra documents of task 3 (corpus_extra/, tools/extra_corpus.py) without network or models:
python tests/test_extra_corpus.py"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.corpus import Corpus
from tools.extra_corpus import EXTRA_DIR, CombinedStore, MemoryStore, load_document, load_extra

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


# --- the files of the repository
docs, chunks = load_extra()
ids = [d["doc_id"] for d in docs]
check("corpus_extra: the two wiki pages", ids == ["wiki_estore_shipping_qa", "wiki_remote_work_faq"])
faq = [c for c in chunks if c["doc_id"] == "wiki_remote_work_faq"]
check("one chunk per '## ' section, numbered like task 2", [c["chunk_id"] for c in faq] ==
      ["wiki_remote_work_faq#0000", "wiki_remote_work_faq#0001", "wiki_remote_work_faq#0002"])
check("the injection is in the FAQ", "ignore all previous instructions" in faq[2]["text"].lower())
check("chunks are linked (prev/next) and carry the front matter",
      faq[0]["prev_id"] is None and faq[0]["next_id"] == faq[1]["chunk_id"] and faq[2]["next_id"] is None
      and faq[1]["year"] == 2025 and faq[1]["date"] == "2025-06-10" and faq[1]["title"] == "Remote Work FAQ (internal wiki)")
check("the section starts with the heading, as in task 2", faq[1]["section"].endswith("> How do I book my remote days?")
      and faq[1]["text"].startswith("How do I book my remote days?"))
need = {"chunk_id", "doc_id", "source_file", "title", "section", "sections", "page_start", "page_end", "year", "version",
        "date", "sha256", "n_words", "position", "prev_id", "next_id", "text"}
check("every chunk has the fields the tools of task 3 read", all(need <= set(c) for c in chunks))
check("a different title: the wiki is not marked as a version of the policy",
      all(d["title"] != "Remote Work Policy" for d in docs))

# --- a file without front matter or sections is refused
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "bad.md"
    for text, why in [("## a\nb", "no front matter"), ("---\ntitle: t\n---\nno sections", "no sections")]:
        p.write_text(text)
        try:
            load_document(p)
            check(f"refused: {why}", False)
        except ValueError:
            check(f"refused: {why}", True)
    check("an empty folder: nothing extra", load_extra(Path(d) / "missing") == ([], []))

# --- Corpus: the extra documents join the chunks and the manifest of task 2
corpus = Corpus()
check("Corpus: the chunks of task 2 and the extra ones", "remote_work_policy#0000" in corpus.chunks
      and "wiki_remote_work_faq#0002" in corpus.chunks)
check("Corpus: the extra documents are listed", {"wiki_remote_work_faq", "wiki_estore_shipping_qa"} <= set(corpus.documents)
      and "remote_work_policy" in corpus.documents)
check("Corpus with test chunks: no extra documents", "wiki_remote_work_faq#0002" not in Corpus(chunks=[], documents=[]).chunks)
check("Corpus(extra_dir=None): only task 2", "wiki_remote_work_faq#0002" not in Corpus(extra_dir=None).chunks)

# --- the stores
fake = [{"chunk_id": "x#0000", "doc_id": "x", "text": "a"}, {"chunk_id": "y#0000", "doc_id": "y", "text": "b"}]
vec = {"a": [1.0, 0.0], "b": [0.6, 0.8]}
mem = MemoryStore(fake, lambda texts: [vec[t] for t in texts])
check("MemoryStore: cosine order", [i for i, _ in mem.query([1.0, 0.0], 5)] == ["x#0000", "y#0000"])
check("MemoryStore: filters as in task 2", [i for i, _ in mem.query([1.0, 0.0], 5, {"doc_id": "y"})] == ["y#0000"])
check("MemoryStore: n limits", len(mem.query([1.0, 0.0], 1)) == 1)


class Fixed:
    def __init__(self, hits):
        self.hits = hits

    def query(self, vector, n, filters=None):
        return self.hits[:n]


both = CombinedStore(Fixed([("p#0000", 0.9), ("p#0001", 0.5)]), Fixed([("q#0000", 0.7)]))
check("CombinedStore: the best of all stores, best first", both.query([0], 2) == [("p#0000", 0.9), ("q#0000", 0.7)])
check("the folder of the repository is corpus_extra/", EXTRA_DIR == ROOT / "corpus_extra")

print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'all checks passed'}")
sys.exit(1 if FAILED else 0)
