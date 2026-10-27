"""One-command entry point: run every model x sampling x prompt, compute metrics, build the table.

    python main.py                                  # all models, samplings and prompt versions from config.yaml
    python main.py --prompt v2                      # one prompt version
    python main.py --models cloud --samplings A     # a part of the grid
    python main.py --force                          # start every run from scratch
    python main.py --redo-failed                    # re-run only the documents that failed

Finished documents are skipped (see src/run.py), so a repeated run on finished results is instant and free.
A model that cannot be reached (no API key, local server not running) is skipped; the metrics and the table are
then built from the results that are already in results/.
Results go to results/*.jsonl and results/metrics_*.json, the comparison table to report/table.md.
"""
import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv

from src.run import result_stem

ROOT = Path(__file__).resolve().parent


def is_local(base_url):
    return urlparse(base_url).hostname in ("localhost", "127.0.0.1")


def reachable(base_url):
    """Cheap check that a server answers (any HTTP answer counts)."""
    try:
        urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=3)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def sh(*args):
    return subprocess.run([sys.executable, "-m", *args], cwd=ROOT).returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", help="keys under models: in config.yaml (default: all)")
    ap.add_argument("--samplings", nargs="+", help="keys under sampling: in config.yaml (default: all)")
    ap.add_argument("--prompt", nargs="+", help="prompt versions (default: prompts: in config.yaml)")
    ap.add_argument("--force", action="store_true", help="redo every run from scratch")
    ap.add_argument("--redo-failed", action="store_true", help="re-run only the documents that failed")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    prompts = args.prompt or cfg["prompts"]
    models = args.models or list(cfg["models"])
    samplings = args.samplings or list(cfg["sampling"])
    for k in models:
        if k not in cfg["models"]:
            sys.exit(f"unknown model key '{k}', choose from {list(cfg['models'])}")
    for s in samplings:
        if s not in cfg["sampling"]:
            sys.exit(f"unknown sampling '{s}', choose from {list(cfg['sampling'])}")

    available = {}
    for k in models:
        m = cfg["models"][k]
        available[k] = False
        if not (m.get("api_key") or os.getenv(m.get("api_key_env", ""))):
            print(f"SKIP {k}: no API key (set {m.get('api_key_env')} in .env); results already in results/ are used")
        elif is_local(m["base_url"]) and not reachable(m["base_url"]):
            print(f"SKIP {k}: {m['base_url']} does not answer (is the local server running?); results already in results/ are used")
        else:
            available[k] = True

    failed = []
    for prompt in prompts:
        for k in models:
            for s in samplings:
                label = f"{k} / sampling {s} / prompt {prompt}"
                log = ROOT / "results" / f"{result_stem(cfg['models'][k]['model'], s, prompt)}.jsonl"
                if available[k]:
                    print(f"\n=== run: {label}", flush=True)
                    run_args = ["src.run", "--model", k, "--sampling", s, "--prompt", prompt]
                    if args.force:
                        run_args.append("--force")
                    if args.redo_failed:
                        run_args.append("--redo-failed")
                    if not sh(*run_args):
                        failed.append(label)
                        continue
                elif log.exists():
                    print(f"\n=== {label}: model not available, using {log.name}", flush=True)
                else:
                    print(f"\n=== {label}: model not available and no results yet, skipped", flush=True)
                    continue
                print(f"--- metrics: {label}", flush=True)
                if not sh("src.metrics", str(log)):
                    failed.append(label + " (metrics)")

    print("\n=== table", flush=True)
    sh("src.eval")
    table = ROOT / "report" / "table.md"
    if table.exists():
        print(table.read_text(encoding="utf-8"))
    if failed:
        print("FAILED:", *failed, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
