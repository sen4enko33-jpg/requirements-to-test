"""Ask a question: python -m rag.answer.cli "How many remote days per week?" [--year 2023] [--doc ID] [--show-context]"""
import argparse
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from ..models import token_counter
from ..retrieval.factory import make_retriever
from . import settings
from .context import build_context

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--year", type=int)
    ap.add_argument("--doc")
    ap.add_argument("--show-context", action="store_true")
    a = ap.parse_args()
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT.parent / ".env")                             # one .env in the repository root is enough
    from ..llm import make_client                                 # config.yaml, models.cloud
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    llm, tokens, retriever = make_client(cfg, "cloud"), token_counter(), make_retriever()
    filters = {k: v for k, v in (("year", a.year), ("doc_id", a.doc)) if v}
    from .generate import answer_question
    if a.show_context:
        hits = retriever.search(a.question, settings.TOP_K, "hybrid_rerank", filters)
        print(build_context(hits, settings.CONTEXT_BUDGET_TOKENS, tokens)[0], "\n" + "-" * 60)
    r = answer_question(a.question, retriever, llm, tokens, filters or None)
    print(r.text)
    for c in r.citations:
        print(f"  [{c['n']}] {c['title']} ({c['doc_id']}), {c['version'] or c['date'] or c['year']}, {c['section']}" + (f", {c['page']}" if c["page"] else ""))
    print(f"reason={r.reason} ok={r.ok} problems={r.problems} tokens={r.tokens_in}/{r.tokens_out} latency={r.latency_s and round(r.latency_s, 1)}s")


if __name__ == "__main__":
    main()
