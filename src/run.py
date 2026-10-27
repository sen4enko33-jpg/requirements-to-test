"""Run one model x sampling config x prompt version over a set of excerpts.

    python -m src.run --model cloud --sampling A --prompt v1                      # all 31 excerpts
    python -m src.run --model cloud --sampling A --prompt v1 --ids 2004_sprat_1   # quick check
    python -m src.run --model cloud --sampling A --prompt v1 --split dev          # prompt tuning

Writes one JSON line per document to results/<model>_<sampling>_<prompt>[_<split>].jsonl
(the format src/metrics.py reads). Existing rows are kept, so an interrupted run resumes;
--redo-failed re-runs failed rows, --force starts from scratch.

Status of a row: ok | partial_failed (valid answer, but some requirements are not copied from the
excerpt even after the repair attempt) | failed (no valid answer).
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

from .clients.base import GenResult
from .prompts import build_prompt, load_template
from .schema import Extraction
from .validate import cap_lines, check_copy, drop_repeats, repair_prompt, validate

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
                              extra_body=m.get("extra_body"), schema_limits=m.get("schema_limits"))


def pick_ids(args):
    if args.ids:
        return args.ids
    splits = json.loads((ROOT / "data" / "splits.json").read_text(encoding="utf-8"))
    if args.split == "all":
        return sorted(i for ids in splits.values() for i in ids)
    return splits[args.split]


def add_results(a, b):
    """Total of two API calls (the first answer and its repair)."""
    def total(x, y):
        return None if x is None and y is None else (x or 0) + (y or 0)
    return GenResult(b.text, a.latency_s + b.latency_s, total(a.tokens_in, b.tokens_in),
                     total(a.tokens_out, b.tokens_out), a.attempts + b.attempts, b.error,
                     total(a.cost_usd, b.cost_usd))


def attempt(client, prompt, source, sampling):
    """One answer for `prompt` plus, if it is invalid or has copy violations, ONE repair.
    `source` is the text the copy check compares against. Returns the state of this answer as a dict."""
    res = client.generate(prompt, Extraction, sampling)
    cap = (getattr(client, "schema_limits", None) or {}).get("requirements")
    extraction, error, copy_note = None, res.error, ""
    n_dup, capped = 0, False               # repeats removed from the accepted answer; it reached the requirements limit
    schema_errors, copy_errors, copy_errors_first, copy_first_total = None, [], None, None
    repair_attempted = repaired = False
    repair_reason = None
    if res.text is not None:               # no text = timeout / truncated / refusal: nothing to repair
        extraction, schema_errors = validate(res.text, Extraction)
        if extraction is not None:
            capped = bool(cap) and len(extraction["requirements"]) >= cap
            extraction, n_dup = drop_repeats(extraction)
            copy_errors = check_copy(extraction, source)
            copy_errors_first = copy_errors or None
            copy_first_total = len(extraction["requirements"])
        if schema_errors or copy_errors:   # one repair attempt for either kind of error, then give up
            repair_attempted = True
            repair_reason = "schema" if schema_errors else "copy"
            problems = schema_errors or cap_lines(copy_errors)
            second = client.generate(repair_prompt(prompt, res.text, problems), Extraction, sampling)
            res = add_results(res, second)
            if second.text is None:
                if extraction is None:
                    error = f"schema validation failed; repair failed: {second.error}"
                else:
                    copy_note = f" (repair failed: {second.error})"
            else:
                new, new_errors = validate(second.text, Extraction)
                new_capped, new_dup = False, 0
                if new is not None:
                    new_capped = bool(cap) and len(new["requirements"]) >= cap
                    new, new_dup = drop_repeats(new)
                new_copy = check_copy(new, source) if new is not None else []
                # a repair of a broken answer is accepted if it is valid; a repair of a valid answer only if it does
                # not make it worse: no more copy violations and no fewer correctly copied requirements
                # (otherwise "fixing" by dropping good requirements, or an empty list, would win)
                if new is not None and (extraction is None or (
                        len(new_copy) <= len(copy_errors)
                        and len(new["requirements"]) - len(new_copy)
                        >= len(extraction["requirements"]) - len(copy_errors))):
                    extraction, copy_errors, repaired = new, new_copy, True
                    n_dup, capped = new_dup, new_capped
                elif extraction is None:
                    error = f"schema validation failed after repair: {new_errors.splitlines()[0]}"
    return {"res": res, "extraction": extraction, "error": error, "copy_note": copy_note,
            "schema_errors": schema_errors, "copy_errors": copy_errors, "copy_errors_first": copy_errors_first,
            "copy_first_total": copy_first_total, "repair_attempted": repair_attempted, "repaired": repaired,
            "repair_reason": repair_reason, "n_dup": n_dup, "capped": capped}


def run_doc(client, doc_id, model_key, prompt_version, sampling_name, sampling):
    text = (ROOT / "data" / "noisy" / f"{doc_id}.txt").read_text(encoding="utf-8")
    a = attempt(client, build_prompt(prompt_version, text), text, sampling)
    res, extraction, error = a["res"], a["extraction"], a["error"]
    copy_errors = a["copy_errors"]
    if extraction is None:
        status = "failed"
    elif copy_errors:
        status = "partial_failed"
        error = (f"copy check failed after repair: {len(copy_errors)} of {len(extraction['requirements'])} "
                 f"requirements are not copied from the excerpt{a['copy_note']}")
    else:
        status, error = "ok", None
    return {
        "doc_id": doc_id, "model": client.name, "model_key": model_key,
        "prompt_version": prompt_version, "sampling_name": sampling_name, "sampling": sampling,
        "status": status, "extraction": extraction, "error": error,
        "repair_attempted": a["repair_attempted"], "repaired": a["repaired"], "repair_reason": a["repair_reason"],
        "validation_errors": a["schema_errors"],   # schema errors of the first answer; None if it was valid
        "copy_errors_first": a["copy_errors_first"],   # copy violations of the first answer; None if there were none
        "copy_first_total": a["copy_first_total"],     # requirements in the first answer (None if it broke the schema)
        "copy_violations": len(copy_errors) if extraction is not None else None,   # in the accepted answer
        "copy_total": len(extraction["requirements"]) if extraction is not None else None,
        "n_duplicates_removed": a["n_dup"],        # repeated requirements dropped from the answer (looping model)
        "requirements_capped": a["capped"],        # the answer reached the requirements limit: may be incomplete
        "schema_limits": getattr(client, "schema_limits", None),
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
    # the full run (all 31 excerpts) is the main result; partial runs are experiments
    out = ROOT / "results" / ("experiments" if args.split != "all" or args.ids else "") / f"{stem}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = {}
    if out.exists() and not args.force:
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["doc_id"]] = r
        stale = [r["doc_id"] for r in rows.values()
                 if r["model"] != client.name or r["sampling"] != sampling
                 or r.get("schema_limits") != getattr(client, "schema_limits", None)]
        if stale:
            sys.exit(f"{out.name} has rows made with a different model, sampling or schema limits "
                     f"({len(stale)} rows); use --force to start over")

    for n, doc_id in enumerate(ids, 1):
        old = rows.get(doc_id)
        if old and (old["status"] != "failed" or not args.redo_failed):
            print(f"[{n}/{len(ids)}] {doc_id} skip ({old['status']})")
            continue
        row = run_doc(client, doc_id, args.model, args.prompt, args.sampling, sampling)
        rows[doc_id] = row
        save(out, [rows[i] for i in ids if i in rows])
        n_req = len(row["extraction"]["requirements"]) if row["extraction"] else "-"
        print(f"[{n}/{len(ids)}] {doc_id} {row['status']} {row['latency_s']}s "
              f"in={row['tokens_in']} out={row['tokens_out']} req={n_req} "
              f"attempts={row['attempts']}"
              + (f" repair={'accepted' if row['repaired'] else 'rejected'}" if row["repair_attempted"] else "")
              + (" capped" if row["requirements_capped"] else "")
              + (f" duplicates_removed={row['n_duplicates_removed']}" if row["n_duplicates_removed"] else "")
              + (f" copy_violations={row['copy_violations']}" if row["copy_violations"] else "")
              + (f" error={row['error']}" if row["error"] else ""))

    done = [rows[i] for i in ids if i in rows]
    m = cfg["models"][args.model]
    tin = sum(r["tokens_in"] or 0 for r in done)
    tout = sum(r["tokens_out"] or 0 for r in done)
    est = (tin * m.get("price_in_per_1m", 0) + tout * m.get("price_out_per_1m", 0)) / 1e6
    reported = [r["cost_usd"] for r in done if r.get("cost_usd") is not None]
    real = f", provider-reported ${sum(reported):.4f}" if reported else ""
    n_part = sum(r["status"] == "partial_failed" for r in done)
    print(f"done: {sum(r['status'] == 'ok' for r in done)}/{len(done)} ok"
          + (f", {n_part} partial_failed" if n_part else "") + f", {sum(r['status'] == 'failed' for r in done)} failed, "
          f"tokens in={tin} out={tout}, est. cost ${est:.4f}{real} -> {out}")


if __name__ == "__main__":
    main()
