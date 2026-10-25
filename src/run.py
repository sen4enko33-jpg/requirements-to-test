"""Run one model x sampling config x prompt version over a set of excerpts.

    python -m src.run --model cloud --sampling A --prompt v1                      # all 31 excerpts
    python -m src.run --model cloud --sampling A --prompt v1 --ids 2004_sprat_1   # quick check
    python -m src.run --model cloud --sampling A --prompt v1 --split dev          # prompt tuning

Writes one JSON line per document to results/<model>_<sampling>_<prompt>[_<split>].jsonl
(the format src/metrics.py reads). Existing rows are kept, so an interrupted run resumes;
--redo-failed re-runs failed rows, --force starts from scratch.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from .prompts import build_prompt, load_template
from .schema import Extraction

ROOT = Path(__file__).resolve().parent.parent


def make_client(cfg, model_key):
    m = cfg["models"][model_key]
    key = m.get("api_key") or os.getenv(m.get("api_key_env", ""))
    if not key:
        sys.exit(f"no API key for models.{model_key}: set {m.get('api_key_env')} in .env or api_key in config.yaml")
    if not m.get("model"):
        sys.exit(f"models.{model_key}.model is empty in config.yaml")
    from .clients.openai_compat import OpenAICompatClient
    return OpenAICompatClient(m["model"], m["base_url"], key, m.get("timeout_s", cfg["timeout_s"]),
                              m.get("max_retries", cfg["max_retries"]), m.get("max_tokens", cfg["max_tokens"]),
                              extra_body=m.get("extra_body"))


def pick_ids(args):
    if args.ids:
        return args.ids
    splits = json.loads((ROOT / "data" / "splits.json").read_text(encoding="utf-8"))
    if args.split == "all":
        return sorted(i for ids in splits.values() for i in ids)
    return splits[args.split]


def run_doc(client, doc_id, model_key, prompt_version, sampling_name, sampling):
    text = (ROOT / "data" / "noisy" / f"{doc_id}.txt").read_text(encoding="utf-8")
    res = client.generate(build_prompt(prompt_version, text), Extraction, sampling)
    extraction, error = None, res.error
    if res.text is not None:
        try:
            extraction = Extraction.model_validate_json(res.text).model_dump(mode="json")
        except ValidationError as e:
            error = f"schema validation failed: {e.error_count()} errors"
    return {
        "doc_id": doc_id, "model": client.name, "model_key": model_key,
        "prompt_version": prompt_version, "sampling_name": sampling_name, "sampling": sampling,
        "status": "ok" if extraction is not None else "failed",
        "extraction": extraction, "error": error,
        "latency_s": round(res.latency_s, 3),
        "tokens_in": res.tokens_in, "tokens_out": res.tokens_out,
        "cost_usd": res.cost_usd, "attempts": res.attempts,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def save(path, rows):
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(path)


def result_stem(model, sampling, prompt):
    """File name (without extension) of the run log for a model x sampling x prompt."""
    safe = re.sub(r"[^\w.-]+", "-", model)
    return f"{safe}_{sampling}_{prompt}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="key under models: in config.yaml (cloud, local)")
    ap.add_argument("--sampling", required=True, help="key under sampling: in config.yaml (A, B)")
    ap.add_argument("--prompt", required=True, help="prompt version, e.g. v1")
    ap.add_argument("--split", default="all", choices=["all", "golden", "dev", "excluded"])
    ap.add_argument("--ids", nargs="+", help="run only these excerpt ids (output goes to adhoc_*.jsonl)")
    ap.add_argument("--redo-failed", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    if args.model not in cfg["models"]:
        sys.exit(f"unknown model key '{args.model}', choose from {list(cfg['models'])}")
    if args.sampling not in cfg["sampling"]:
        sys.exit(f"unknown sampling '{args.sampling}', choose from {list(cfg['sampling'])}")
    sampling = cfg["sampling"][args.sampling]
    load_template(args.prompt)  # fail early if the prompt version is missing or broken

    ids = pick_ids(args)
    absent = [i for i in ids if not (ROOT / "data" / "noisy" / f"{i}.txt").exists()]
    if absent:
        sys.exit(f"no text in data/noisy for: {absent}")

    client = make_client(cfg, args.model)
    stem = result_stem(client.name, args.sampling, args.prompt)
    if args.ids:
        stem = "adhoc_" + stem
    elif args.split != "all":
        stem += f"_{args.split}"
    out = ROOT / "results" / f"{stem}.jsonl"
    out.parent.mkdir(exist_ok=True)

    rows = {}
    if out.exists() and not args.force:
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["doc_id"]] = r
        stale = [r["doc_id"] for r in rows.values()
                 if r["model"] != client.name or r["sampling"] != sampling]
        if stale:
            sys.exit(f"{out.name} has rows made with a different model or sampling "
                     f"({len(stale)} rows); use --force to start over")

    for n, doc_id in enumerate(ids, 1):
        old = rows.get(doc_id)
        if old and (old["status"] == "ok" or not args.redo_failed):
            print(f"[{n}/{len(ids)}] {doc_id} skip ({old['status']})")
            continue
        row = run_doc(client, doc_id, args.model, args.prompt, args.sampling, sampling)
        rows[doc_id] = row
        save(out, [rows[i] for i in ids if i in rows])
        n_req = len(row["extraction"]["requirements"]) if row["extraction"] else "-"
        print(f"[{n}/{len(ids)}] {doc_id} {row['status']} {row['latency_s']}s "
              f"in={row['tokens_in']} out={row['tokens_out']} req={n_req} "
              f"attempts={row['attempts']}" + (f" error={row['error']}" if row["error"] else ""))

    done = [rows[i] for i in ids if i in rows]
    m = cfg["models"][args.model]
    tin = sum(r["tokens_in"] or 0 for r in done)
    tout = sum(r["tokens_out"] or 0 for r in done)
    est = (tin * m.get("price_in_per_1m", 0) + tout * m.get("price_out_per_1m", 0)) / 1e6
    reported = [r["cost_usd"] for r in done if r.get("cost_usd") is not None]
    real = f", provider-reported ${sum(reported):.4f}" if reported else ""
    print(f"done: {sum(r['status'] == 'ok' for r in done)}/{len(done)} ok, "
          f"tokens in={tin} out={tout}, est. cost ${est:.4f}{real} -> {out}")


if __name__ == "__main__":
    main()
