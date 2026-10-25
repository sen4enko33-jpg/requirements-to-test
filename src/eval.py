"""Collect results/metrics_*.json into results/summary.csv (all metrics)
and report/table.md (the four required metrics per model x sampling x prompt)."""
import csv
import json
from pathlib import Path


def flatten(d, prefix=""):
    flat = {}
    for k, v in d.items():
        if k == "per_doc":
            continue
        if isinstance(v, dict):
            flat.update(flatten(v, f"{prefix}{k}."))
        else:
            flat[f"{prefix}{k}"] = v
    return flat


Q = "quality_all_docs."
ACC_COLS = [
    ("doc_title", Q + "scalar_accuracy.doc_title"),
    ("domain", Q + "scalar_accuracy.domain"),
    ("language", Q + "scalar_accuracy.language"),
    ("acceptance", Q + "scalar_accuracy.has_acceptance_criteria"),
    ("actors (F1)", Q + "actors.f1"),
    ("req.type", Q + "requirement_field_accuracy_strict.type"),
    ("req.testable", Q + "requirement_field_accuracy_strict.testable"),
    ("req.id", Q + "requirement_field_accuracy_strict.id"),
    ("req.section", Q + "requirement_field_accuracy_strict.section"),
]


def num(x, fmt):
    return "n/a" if x is None else format(x, fmt)


def main():
    flats = [flatten(json.loads(p.read_text(encoding="utf-8")))
             for p in sorted(Path("results").glob("metrics_*.json"))]
    if not flats:
        raise SystemExit("no results/metrics_*.json found")

    header = list(dict.fromkeys(k for f in flats for k in f))
    with open("results/summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        w.writerows(flats)

    cols = (["model", "sampling", "prompt"] + [c for c, _ in ACC_COLS]
            + ["valid %", "p50 s", "p95 s", "$ / 1000 docs"])
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for f in flats:
        row = [f["meta.model"], f["meta.sampling_name"], f["meta.prompt_version"]]
        row += [num(100 * f[k], ".0f") + "%" for _, k in ACC_COLS]
        row += [num(f["operational.valid_pct"], ".0f") + "%",
                num(f["operational.latency_p50_s"], ".1f"),
                num(f["operational.latency_p95_s"], ".1f"),
                "$" + num(f["operational.cost_per_1000_docs_usd"], ".2f")]
        lines.append("| " + " | ".join(row) + " |")
    Path("report").mkdir(exist_ok=True)
    Path("report/table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("-> results/summary.csv, report/table.md")


if __name__ == "__main__":
    main()
