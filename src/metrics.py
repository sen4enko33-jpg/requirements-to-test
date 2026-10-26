"""Metrics for one run log (results/<model>_<sampling>_<prompt>.jsonl).

Quality (field accuracy, requirement matching) is computed on the golden split only.
Operational metrics (valid %, latency, cost) use every row of the run log;
latency percentiles are taken over successful responses (the *_all_* keys include failed calls).
Everything is recomputed from the raw log, so changing a threshold needs no new API calls.

Run-log row: doc_id, model, prompt_version, sampling_name, sampling,
status ("ok" | "partial_failed" | "failed"), extraction (dict | None), error, latency_s,
tokens_in, tokens_out, attempts.
"""
import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from .validate import check_copy

MATCH_THRESHOLD = 0.75  # min similarity to pair a predicted requirement with a golden one
COVER_THRESHOLD = 0.80  # min token coverage to call an unmatched requirement merged/split
ACTOR_MATCH_THRESHOLD = 0.80  # actors are paired by similarity too, so "analyst" and "analysts" match
MATCH_MIN_COVER = 0.70  # both texts must share this token share to be paired (rejects shared-boilerplate matches)
SCALARS = ["doc_title", "domain", "language", "has_acceptance_criteria"]
REQ_FIELDS = ["type", "testable", "id", "section"]


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower()).strip(" .;:-")


def tokens(s):
    return Counter(re.findall(r"\w+", s.lower()))


def similarity(a, b):
    return SequenceMatcher(None, norm(a), norm(b), autojunk=False).ratio()


def cover(a, b):
    """Share of the tokens of `a` that also occur in `b`."""
    ta, tb = tokens(a), tokens(b)
    total = sum(ta.values())
    return sum((ta & tb).values()) / total if total else 0.0


VALID_STATUSES = ("ok", "partial_failed")   # a valid answer exists (partial_failed: some requirements not copied)
TEXTS_DIR = Path(__file__).resolve().parent.parent / "data" / "noisy"


def div(a, b):
    return a / b if b else 0.0


def mean(xs):
    return div(sum(xs), len(xs))


def prf(tp, n_gold, n_pred):
    p, r = div(tp, n_pred), div(tp, n_gold)
    return {"precision": p, "recall": r, "f1": div(2 * p * r, p + r)}


def percentile(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def match(gold, pred, threshold):
    """Greedy one-to-one pairing of requirements by text similarity.

    A pair needs a high character similarity AND mutual token coverage, so a short
    fragment that only shares the boilerplate ("The system shall ...") is not a match.
    """
    cands = []
    for i, g in enumerate(gold):
        for j, p in enumerate(pred):
            sim = similarity(g["text"], p["text"])
            if sim >= threshold and min(cover(g["text"], p["text"]),
                                        cover(p["text"], g["text"])) >= MATCH_MIN_COVER:
                cands.append((sim, i, j))
    cands.sort(reverse=True)
    used_g, used_p, pairs = set(), set(), []
    for sim, i, j in cands:
        if i in used_g or j in used_p:
            continue
        used_g.add(i)
        used_p.add(j)
        pairs.append((i, j, sim))
    return pairs


def match_strings(gold, pred, threshold):
    """Number of one-to-one pairs between two lists of short strings (actors), by similarity."""
    cands = sorted(((similarity(g, p), i, j)
                    for i, g in enumerate(gold) for j, p in enumerate(pred)), reverse=True)
    used_g, used_p, n = set(), set(), 0
    for sim, i, j in cands:
        if sim < threshold:
            break
        if i in used_g or j in used_p:
            continue
        used_g.add(i)
        used_p.add(j)
        n += 1
    return n


def diagnose(gold, pred, pairs):
    """Classify unmatched requirements: merged / split / missed / extra."""
    matched_g = {p[0] for p in pairs}
    matched_p = {p[1] for p in pairs}
    ug = [i for i in range(len(gold)) if i not in matched_g]
    up = [j for j in range(len(pred)) if j not in matched_p]

    merged_g, merged_p = set(), set()  # one predicted requirement covers >= 2 golden ones
    for j in up:
        covered = [i for i in ug if cover(gold[i]["text"], pred[j]["text"]) >= COVER_THRESHOLD]
        if len(covered) >= 2:
            merged_p.add(j)
            merged_g.update(covered)

    split_g, split_p = set(), set()  # one golden requirement covered by >= 2 predicted ones
    for i in ug:
        if i in merged_g:
            continue
        parts = [j for j in up if j not in merged_p
                 and cover(pred[j]["text"], gold[i]["text"]) >= COVER_THRESHOLD]
        joined = " ".join(pred[j]["text"] for j in parts)
        if len(parts) >= 2 and cover(gold[i]["text"], joined) >= COVER_THRESHOLD:
            split_g.add(i)
            split_p.update(parts)

    return {"merged": len(merged_p), "split": len(split_g),
            "missed": len(set(ug) - merged_g - split_g),
            "extra": len(set(up) - merged_p - split_p)}


def score_doc(gold, row, threshold=MATCH_THRESHOLD):
    pred = row.get("extraction") if row["status"] in VALID_STATUSES else None
    failed = pred is None
    pred = pred or {}

    scalars = {f: int(not failed and norm(str(gold[f])) == norm(str(pred.get(f)))) for f in SCALARS}

    ga = sorted({norm(a) for a in gold["actors"]})
    pa = sorted({norm(a) for a in pred.get("actors", [])})

    greq, preq = gold["requirements"], pred.get("requirements", [])
    pairs = match(greq, preq, threshold)
    field_correct = {f: sum(norm(greq[i].get(f)) == norm(preq[j].get(f)) for i, j, _ in pairs)
                     for f in REQ_FIELDS}

    return {
        "doc_id": row["doc_id"],
        "failed": failed,
        "scalars": scalars,
        "actors": {"tp": match_strings(ga, pa, ACTOR_MATCH_THRESHOLD), "n_gold": len(ga), "n_pred": len(pa)},
        "requirements": {
            "tp": len(pairs), "n_gold": len(greq), "n_pred": len(preq),
            "field_correct": field_correct,
            **diagnose(greq, preq, pairs),
            "pairs": [[i, j, round(s, 3)] for i, j, s in pairs],
        },
        "open_questions": {"n_gold": len(gold["open_questions"]),
                           "n_pred": len(pred.get("open_questions", []))},
    }


def aggregate(docs):
    req = [d["requirements"] for d in docs]
    act = [d["actors"] for d in docs]
    gold_total = sum(r["n_gold"] for r in req)
    tp_total = sum(r["tp"] for r in req)
    return {
        "n_docs": len(docs),
        "scalar_accuracy": {f: mean([d["scalars"][f] for d in docs]) for f in SCALARS},
        "actors": {
            **prf(sum(a["tp"] for a in act), sum(a["n_gold"] for a in act), sum(a["n_pred"] for a in act)),
            "f1_macro": mean([prf(a["tp"], a["n_gold"], a["n_pred"])["f1"] for a in act]),
        },
        "requirements": {
            **prf(tp_total, gold_total, sum(r["n_pred"] for r in req)),
            "f1_macro": mean([prf(r["tp"], r["n_gold"], r["n_pred"])["f1"] for r in req]),
            "n_gold": gold_total, "tp": tp_total,
            "merged": sum(r["merged"] for r in req), "split": sum(r["split"] for r in req),
            "missed": sum(r["missed"] for r in req), "extra": sum(r["extra"] for r in req),
        },
        # strict: a requirement that was not found counts as wrong
        "requirement_field_accuracy_strict": {
            f: div(sum(r["field_correct"][f] for r in req), gold_total) for f in REQ_FIELDS},
        # matched: only requirements the model found
        "requirement_field_accuracy_matched": {
            f: div(sum(r["field_correct"][f] for r in req), tp_total) for f in REQ_FIELDS},
        "open_questions": {"n_gold": sum(d["open_questions"]["n_gold"] for d in docs),
                           "n_pred": sum(d["open_questions"]["n_pred"] for d in docs)},
    }


def copy_stats(rows, texts_dir):
    """How many requirements are not copied from the excerpt (check_copy), in the final answers and,
    where the log has it, in the first answers before the repair attempt."""
    viol = total = first_viol = first_total = docs_with = 0
    for r in rows:
        ext = r.get("extraction")
        if not ext or texts_dir is None:
            continue
        n_bad = len(check_copy(ext, (Path(texts_dir) / f"{r['doc_id']}.txt").read_text(encoding="utf-8")))
        n_req = len(ext["requirements"])
        viol, total, docs_with = viol + n_bad, total + n_req, docs_with + bool(n_bad)
        if r.get("copy_first_total") is not None:      # new log: the first answer is stored
            first_viol += len(r.get("copy_errors_first") or [])
            first_total += r["copy_first_total"]
        elif "repair_attempted" not in r:               # old log: there was no repair, first = final
            first_viol, first_total = first_viol + n_bad, first_total + n_req
    return {"n_requirements_checked": total, "n_copy_violations": viol,
            "copy_violation_pct": 100 * div(viol, total),
            "copy_violation_pct_first_try": 100 * div(first_viol, first_total),
            "n_docs_with_copy_violations": docs_with}


def operational(rows, price_in, price_out, texts_dir=None):
    n = len(rows)
    valid = [r for r in rows if r["status"] in VALID_STATUSES]
    n_partial = sum(1 for r in rows if r["status"] == "partial_failed")
    lat_ok = [r["latency_s"] for r in valid if r.get("latency_s") is not None]
    lat_all = [r["latency_s"] for r in rows if r.get("latency_s") is not None]
    tin = sum(r.get("tokens_in") or 0 for r in rows)
    tout = sum(r.get("tokens_out") or 0 for r in rows)
    n_empty = sum(1 for r in valid if not (r.get("extraction") or {}).get("requirements"))
    n_repaired = sum(1 for r in valid if r.get("repaired"))
    n_repair_attempted = sum(1 for r in rows if r.get("repair_attempted"))
    n_capped = sum(1 for r in rows if r.get("requirements_capped"))
    n_dups = sum(r.get("n_duplicates_removed") or 0 for r in rows)
    n_schema_repaired = sum(1 for r in valid if r.get("repaired") and r.get("repair_reason") in (None, "schema"))
    return {
        # valid = a schema-valid answer exists (ok + partial_failed); failed = no valid answer
        "n_rows": n, "n_failed": n - len(valid), "valid_pct": 100 * div(len(valid), n),
        "n_partial_failed": n_partial, "partial_failed_pct": 100 * div(n_partial, n),
        # share of answers that were schema-valid on the first try (valid_pct also counts those fixed by the repair)
        "valid_first_try_pct": 100 * div(len(valid) - n_schema_repaired, n),
        "n_capped": n_capped, "capped_pct": 100 * div(n_capped, n), "n_duplicates_removed": n_dups,
        "n_repair_attempted": n_repair_attempted, "n_repaired": n_repaired,
        **copy_stats(valid, texts_dir),
        # valid JSON but no requirements at all: a silent failure that valid_pct does not see
        "n_empty": n_empty, "empty_pct": 100 * div(n_empty, n),
        # latency of successful responses; failed calls (timeouts) would distort the percentiles
        "latency_p50_s": percentile(lat_ok, 0.5), "latency_p95_s": percentile(lat_ok, 0.95),
        "latency_all_p50_s": percentile(lat_all, 0.5), "latency_all_p95_s": percentile(lat_all, 0.95),
        "tokens_in_total": tin, "tokens_out_total": tout,
        "mean_attempts": mean([r.get("attempts") or 1 for r in rows]),
        "cost_per_1000_docs_usd": div(tin * price_in + tout * price_out, n) / 1e6 * 1000,
    }


def evaluate(rows, golden_dir, golden_ids, prices, threshold):
    by_id = {r["doc_id"]: r for r in rows}
    missing = [g for g in golden_ids if g not in by_id]
    if missing:
        raise SystemExit(f"run log has no rows for golden ids: {missing}")
    docs = []
    for g in golden_ids:
        gold = json.loads((golden_dir / f"{g}.json").read_text(encoding="utf-8"))
        docs.append(score_doc(gold, by_id[g], threshold))
    price_in, price_out = prices.get(rows[0]["model"], (0.0, 0.0))
    return {
        "operational": operational(rows, price_in, price_out, TEXTS_DIR),
        "quality_all_docs": aggregate(docs),  # failed documents count as zeros
        "quality_valid_only": aggregate([d for d in docs if not d["failed"]]),
        "per_doc": docs,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_log")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--splits", default="data/splits.json")
    ap.add_argument("--golden-dir", default="data/golden")
    ap.add_argument("--threshold", type=float, default=MATCH_THRESHOLD)
    args = ap.parse_args()

    import yaml
    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    prices = {m["model"]: (m.get("price_in_per_1m", 0.0), m.get("price_out_per_1m", 0.0))
              for m in cfg["models"].values()}
    rows = [json.loads(l) for l in open(args.run_log, encoding="utf-8") if l.strip()]
    golden_ids = json.load(open(args.splits, encoding="utf-8"))["golden"]

    first = rows[0]
    result = {
        "meta": {
            "model": first["model"], "prompt_version": first["prompt_version"],
            "sampling_name": first["sampling_name"], "sampling": first["sampling"],
            "run_log": args.run_log, "split": "golden",
            "match_threshold": args.threshold, "cover_threshold": COVER_THRESHOLD,
            "actor_match_threshold": ACTOR_MATCH_THRESHOLD,
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        **evaluate(rows, Path(args.golden_dir), golden_ids, prices, args.threshold),
    }
    out = Path("results") / f"metrics_{Path(args.run_log).stem}_golden.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
