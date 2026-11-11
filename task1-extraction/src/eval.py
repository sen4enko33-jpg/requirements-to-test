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
# (column, metric key, number format); quality is measured on the golden set
QUALITY_COLS = [
    ("doc_title", Q + "scalar_accuracy.doc_title", "pct"),
    ("domain", Q + "scalar_accuracy.domain", "pct"),
    ("language", Q + "scalar_accuracy.language", "pct"),
    ("acceptance", Q + "scalar_accuracy.has_acceptance_criteria", "pct"),
    ("actors F1", Q + "actors.f1", "f"),
    ("req. P", Q + "requirements.precision", "f"),
    ("req. R", Q + "requirements.recall", "f"),
    ("req. F1", Q + "requirements.f1", "f"),
    ("type", Q + "requirement_field_accuracy_strict.type", "pct"),
    ("testable", Q + "requirement_field_accuracy_strict.testable", "pct"),
    ("id", Q + "requirement_field_accuracy_strict.id", "pct"),
    ("section", Q + "requirement_field_accuracy_strict.section", "pct"),
    ("section (last heading)", Q + "requirement_field_accuracy_strict.section_leaf", "pct"),
]
# reliability, speed and cost: measured on all 31 excerpts
OPERATIONAL_COLS = [
    ("valid %", "operational.valid_pct", "p0"),
    ("partial %", "operational.partial_failed_pct", "p0"),
    ("copy viol. %", "operational.copy_violation_pct", "p1"),
    ("empty %", "operational.empty_pct", "p0"),
    ("capped %", "operational.capped_pct", "p0"),
    ("p50 s", "operational.latency_p50_s", "s"),
    ("p95 s", "operational.latency_p95_s", "s"),
    ("USD / 1000 docs", "operational.cost_per_1000_docs_usd", "usd"),
]


def num(x, fmt):
    return "n/a" if x is None else format(x, fmt)


def pct(x, fmt):
    return "n/a" if x is None else format(x, fmt) + "%"


def cell(f, key, kind):
    v = f.get(key)
    if v is None:
        return "n/a"
    return {"pct": lambda: format(100 * v, ".0f") + "%", "f": lambda: format(v, ".2f"),
            "p0": lambda: format(v, ".0f") + "%", "p1": lambda: format(v, ".1f") + "%",
            "s": lambda: format(v, ".1f"), "usd": lambda: format(v, ".2f") + " USD"}[kind]()


def table(flats, cols):
    head = ["model", "sampling", "prompt"] + [c for c, _, _ in cols]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for f in flats:
        row = [f["meta.model"], f["meta.sampling_name"], f["meta.prompt_version"]]
        row += [cell(f, k, kind) for _, k, kind in cols]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def main():
    flats = [flatten(json.loads(p.read_text(encoding="utf-8")))
             for p in sorted(Path("results").glob("metrics_*.json"))]
    if not flats:
        raise SystemExit("no results/metrics_*.json found")
    flats.sort(key=lambda f: (f["meta.model"], f["meta.prompt_version"], f["meta.sampling_name"]))

    header = list(dict.fromkeys(k for f in flats for k in f))
    with open("results/summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        w.writerows(flats)

    text = ("## Quality (golden set: 10 excerpts, 158 gold requirements)\n\n" + table(flats, QUALITY_COLS)
            + "\n\n## Reliability, speed, cost (all 31 excerpts)\n\n" + table(flats, OPERATIONAL_COLS) + "\n")
    Path("report").mkdir(exist_ok=True)
    Path("report/table.md").write_text(text, encoding="utf-8")
    print("-> results/summary.csv, report/table.md")


if __name__ == "__main__":
    main()
