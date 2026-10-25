"""Build data/splits.json: golden / dev / excluded, split by source document.

golden   - labeled excerpts; used only for final metrics, never for tuning prompts
dev      - excerpts from documents that have no golden excerpt; used to tune prompts
excluded - the other excerpt of each golden document (too similar to golden); unused
"""
import csv
import json
from pathlib import Path

DATA = Path("data")


def main() -> None:
    golden = (DATA / "golden" / "golden_ids.txt").read_text().split()
    rows = list(csv.DictReader(open(DATA / "index.csv", encoding="utf-8")))
    doc_of = {r["text_id"]: r["source_file"] for r in rows}

    unknown = [g for g in golden if g not in doc_of]
    assert not unknown, f"golden ids missing from index.csv: {unknown}"

    golden_docs = {doc_of[g] for g in golden}
    dev = [r["text_id"] for r in rows if r["source_file"] not in golden_docs]
    excluded = [r["text_id"] for r in rows
                if r["source_file"] in golden_docs and r["text_id"] not in golden]
    splits = {"golden": golden, "dev": dev, "excluded": excluded}

    # every excerpt in exactly one split
    all_ids = [i for ids in splits.values() for i in ids]
    assert len(all_ids) == len(set(all_ids)), "an id appears in more than one split"
    assert set(all_ids) == set(doc_of), "some excerpts are not assigned to any split"
    # no document shared between golden and dev
    dev_docs = {doc_of[i] for i in dev}
    assert not (golden_docs & dev_docs), "golden and dev share a document"
    # every input file exists
    missing = [i for i in all_ids if not (DATA / "noisy" / f"{i}.txt").exists()]
    assert not missing, f"missing files in data/noisy: {missing}"

    (DATA / "splits.json").write_text(
        json.dumps(splits, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print({k: len(v) for k, v in splits.items()}, "-> data/splits.json")


if __name__ == "__main__":
    main()
