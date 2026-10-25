"""One-command entry point: run every model x sampling x prompt, compute metrics, build the table.

    python main.py                                  # all models and samplings from config.yaml, prompt v1
    python main.py --prompt v1 v2                   # several prompt versions
    python main.py --models cloud --samplings A     # a part of the grid
    python main.py --force                          # start every run from scratch
    python main.py --redo-failed                    # re-run only the documents that failed

Finished documents are skipped (see src/run.py), so a repeated run on finished results is instant and free.
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
    ap.add_argument("--prompt", nargs="+", default=["v1"], help="prompt versions (default: v1)")
    ap.add_argument("--force", action="store_true", help="redo every run from scratch")
    ap.add_argument("--redo-failed", action="store_true", help="re-run only the documents that failed")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    models = args.models or list(cfg["models"])
    samplings = args.samplings or list(cfg["sampling"])
    for k in models:
        if k not in cfg["models"]:
            sys.exit(f"unknown model key '{k}', choose from {list(cfg['models'])}")
    for s in samplings:
        if s not in cfg["sampling"]:
            sys.exit(f"unknown sampling '{s}', choose from {list(cfg['sampling'])}")

    usable = []
    for k in models:
        m = cfg["models"][k]
        if not (m.get("api_key") or os.getenv(m.get("api_key_env", ""))):
            sys.exit(f"models.{k}: no API key, set {m.get('api_key_env')} in .env")
        if is_local(m["base_url"]) and not reachable(m["base_url"]):
            print(f"SKIP {k}: {m['base_url']} does not answer (is the local server running?)")
            continue
        usable.append(k)
    if not usable:
        sys.exit("nothing to run")

    failed = []
    for prompt in args.prompt:
        for k in usable:
            for s in samplings:
                label = f"{k} / sampling {s} / prompt {prompt}"
                print(f"\n=== run: {label}", flush=True)
                run_args = ["src.run", "--model", k, "--sampling", s, "--prompt", prompt]
                if args.force:
                    run_args.append("--force")
                if args.redo_failed:
                    run_args.append("--redo-failed")
                if not sh(*run_args):
                    failed.append(label)
                    continue
                log = ROOT / "results" / f"{result_stem(cfg['models'][k]['model'], s, prompt)}.jsonl"
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
