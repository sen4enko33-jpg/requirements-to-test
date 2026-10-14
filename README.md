# requirements-to-test

Extract structured requirements from messy text excerpts (taken from the PURE requirements
documents) using a schema, and compare a paid cloud model with a local model:
field-level accuracy, response validity, latency, and cost.

## Structure
- `data/texts` — clean text excerpts cut from the PDFs (31 files)
- `data/noisy` — the same excerpts with injected noise (typos, dropped sentences, Ukrainian sentences); these are the model inputs
- `data/golden` — manually labeled ground truth for 10 of the texts (`golden_ids.txt` lists them)
- `data/index.csv`, `data/noise_log.csv` — excerpt metadata and the log of injected noise
- `src/schema.py` — Pydantic schema of the extraction result
- `src/prompts.py` — loads a prompt version and inserts the document text
- `prompts/` — prompt versions (`extract_v1.md`, …)
- `CHANGELOG.md` — what changed between prompt versions and why
- `results/` — run logs (jsonl); `report/` — final comparison

## Setup
Python 3.10+ (the schema uses `X | None`).

    pip install -r requirements.txt
    cp .env.example .env      # then put your ANTHROPIC_API_KEY into .env

Rebuilding the data from PDFs additionally needs `pdftotext` (poppler) and the PURE PDFs;
set `SRC_DIR` in `pdf_to_raw_data.py` to the folder with them.

## Data pipeline
1. `python pdf_to_raw_data.py` — PDF to text, two excerpts per document (seed 42) into `data/texts`, metadata into `data/index.csv`.
2. `python add_noise.py` — injects noise (seed 7) into `data/noisy`, log in `data/noise_log.csv`.
3. Golden labels are written by hand in `data/golden/<text_id>.json` and checked against the schema:

       python check_golden.py

## Schema
`Extraction` (`src/schema.py`): `doc_title`, `domain` (enum), `language` (enum), `actors` (list),
`requirements` (list of `Requirement`: `id`, `section`, `text`, `type`, `testable`),
`has_acceptance_criteria`, `open_questions`. Field descriptions are repeated in the prompt text
so the cloud and the local model see the same information.

## Prompts
Build a prompt for a document:

    from src.prompts import build_prompt
    prompt = build_prompt("v1", document_text)

Versions and their rationale are in `CHANGELOG.md`.

## Labeling conventions (golden set)
- One requirement per complete statement; a list under a single "shall" is one requirement.
- `text` is copied as written in the source, including typos; layout artifacts are removed.
- `id` only if written in the text; `section` is the heading path joined with " > ".
- `open_questions` only for items the text itself marks as unresolved.

## Usage
Running the models and the evaluation (clients, `run.py`, `eval.py`) is added in step 2.
