"""One command for the whole RAG part:  python main.py

  python main.py                      # ingestion -> chunking -> index -> retrieval metrics -> answers to the 28 test questions + scorers
  python main.py "your question"      # builds what is missing (the index) and answers one question with citations
  python main.py --steps index,answers --judge   # only some steps; --judge adds the LLM judge (needs the API key, costs money)

Steps (in order): ingest, chunk, index, retrieval, answers. Every step reuses what is already built (cached extraction, an index that is
up to date), so a second run is fast. The model steps (answers, judge) need OPENROUTER_API_KEY in .env (repository root or this
folder); without it they are skipped with a message and everything else still runs. The index is stored in rag/data/chroma, or in
RAG_CHROMA_DIR (use it when this folder is on a network disk: SQLite does not work there)."""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
PROMPT = "v3"                                    # the answer prompt measured best in REPORT.md
STEPS = ("ingest", "chunk", "index", "retrieval", "answers")


def run(*module_args: str) -> int:
    print("\n$ python -m " + " ".join(module_args), flush=True)
    return subprocess.run([sys.executable, "-m", *module_args], cwd=ROOT).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="?", help="answer one question instead of running the pipeline")
    ap.add_argument("--steps", default=",".join(STEPS), help=f"comma-separated subset of: {', '.join(STEPS)}")
    ap.add_argument("--judge", action="store_true", help="also run the LLM judge on the answers (costs money)")
    ap.add_argument("--prompt", default=PROMPT, help="answer prompt version (rag/prompts/answer_<version>.md)")
    a = ap.parse_args()
    load_dotenv(ROOT / ".env"); load_dotenv(ROOT.parent / ".env")
    has_key = bool(os.getenv("OPENROUTER_API_KEY"))
    steps = [s.strip() for s in a.steps.split(",") if s.strip()]
    if a.question:
        steps = ["index"]
    bad = [s for s in steps if s not in STEPS]
    if bad:
        sys.exit(f"unknown step(s): {bad}; choose from {STEPS}")
    t = time.time()
    if "ingest" in steps and run("rag.ingest.cli"):
        return 1
    if "chunk" in steps and run("rag.chunking.cli"):
        return 1
    if "index" in steps and run("rag.retrieval.build"):
        return 1
    if "retrieval" in steps and (run("rag.chunking.cli", "--fixed") or run("rag.retrieval.build", "--fixed") or run("rag.eval.run_retrieval")):
        return 1
    if a.question:
        if not has_key:
            sys.exit("no OPENROUTER_API_KEY: copy .env.example to .env and put the key there")
        return run("rag.answer.cli", a.question)
    if "answers" in steps:
        if not has_key:
            print("\nSkipped: answers and judge (no OPENROUTER_API_KEY in .env).")
        else:
            if run("rag.eval.run_answers", "--prompt", a.prompt):
                return 1
            if a.judge and run("rag.eval.run_judge", a.prompt):
                return 1
            if run("rag.eval.check_thresholds", "answers", a.prompt):
                return 1
    print(f"\nDone in {time.time() - t:.0f} s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
