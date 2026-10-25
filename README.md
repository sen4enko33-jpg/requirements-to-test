# requirements-to-test

Extract structured requirements from messy text excerpts (taken from the PURE requirements
documents) using a schema, and compare a paid cloud model with a local model:
field-level accuracy, response validity, latency, and cost.

## Structure
- `data/texts` — clean text excerpts cut from the PDFs (31 files)
- `data/noisy` — the same excerpts with injected noise (typos, dropped sentences, Ukrainian sentences); these are the model inputs
- `data/golden` — manually labeled ground truth for 10 of the texts (`golden_ids.txt` lists them)
- `data/index.csv`, `data/noise_log.csv` — excerpt metadata and the log of injected noise
- `data/splits.json` — golden / dev / excluded split of the excerpts (built by `make_splits.py`)
- `src/schema.py` — Pydantic schema of the extraction result
- `src/prompts.py` — loads a prompt version and inserts the document text
- `src/clients/` — model clients behind one interface (`base.py`); `openai_compat.py` serves both OpenRouter and Ollama
- `src/run.py` — runs a model x sampling x prompt over the excerpts and writes `results/*.jsonl`
- `src/metrics.py`, `src/eval.py` — metrics per run and the comparison table
- `config.yaml` — models, prices, timeouts, sampling configs
- `prompts/` — prompt versions (`extract_v1.md`, …)
- `CHANGELOG.md` — what changed between prompt versions and why
- `results/` — run logs (jsonl); `report/` — final comparison

## Data source
The excerpts come from the PURE dataset of public software requirements documents (79 PDFs):
https://zenodo.org/records/1414117, licensed CC BY 4.0. The PDFs are not included in this repository.
`data/texts` holds excerpts cut from them, `data/noisy` the same excerpts with artificial noise added by
`add_noise.py`, `data/golden` the annotations written by hand. The excerpts and annotations are shared under the
same license, with attribution to the original dataset.

## Setup
Python 3.10+ (the schema uses `X | None`).

    pip install -r requirements.txt
    cp .env.example .env      # then put your OPENROUTER_API_KEY into .env

Local model (Ollama): `ollama pull llama3.2:3b`, then start the server with a context large enough for the
prompts: `OLLAMA_CONTEXT_LENGTH=8192 ollama serve`. The OpenAI-compatible endpoint cannot set the context
per request, and with a small default Ollama silently cuts the beginning of the prompt.

Rebuilding the data from PDFs additionally needs `pdftotext` (poppler) and the PURE PDFs;
set `SRC_DIR` in `pdf_to_raw_data.py` to the folder with them.

## Data pipeline
1. `python pdf_to_raw_data.py` — PDF to text, two excerpts per document (seed 42) into `data/texts`, metadata into `data/index.csv`.
2. `python add_noise.py` — injects noise (seed 7) into `data/noisy`, log in `data/noise_log.csv`.
3. Golden labels are written by hand in `data/golden/<text_id>.json` and checked against the schema:

       python check_golden.py

## Data splits
Excerpts are split by source document (two excerpts per document, so splitting by excerpt would leak):

- `golden` (10) — labeled; used only for final metrics, prompts are never tuned on it
- `dev` (11) — excerpts of the 6 documents that have no golden excerpt; used to tune prompts (v2+), no labels, errors are reviewed by hand
- `excluded` (10) — the other excerpt of each golden document; too similar to golden, not used

Prompt v1 was written after reading the golden texts, so it partly saw them; later versions are
justified by dev errors only (see `CHANGELOG.md`).

    python make_splits.py

## Schema
`Extraction` (`src/schema.py`): `doc_title`, `domain` (enum), `language` (enum), `actors` (list),
`requirements` (list of `Requirement`: `id`, `section`, `text`, `type`, `testable`),
`has_acceptance_criteria`, `open_questions`. Field descriptions live only in the schema and reach
the model through structured output; the prompt holds only rules the schema cannot express.

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
- Sentences in another language (injected Ukrainian sentences) are labeled like any other text: if the sentence is a requirement it is extracted as written, without translation; the document-level `language` field is not changed by them.

## Usage
The whole pipeline in one command (all models x sampling configs from `config.yaml`, then metrics and the table):

    python main.py                                  # prompt v1
    python main.py --models cloud --samplings A     # a part of the grid
    python main.py --prompt v1 v2                   # several prompt versions

Finished documents are skipped, so a repeated run on finished results is instant and free. **To restart from
scratch, pass `--force`**: it discards the existing run logs and redoes every run (this costs money again for the cloud
model). It is also required after changing a model or a sampling config in `config.yaml`, because the old rows were
made with different settings and `src.run` refuses to mix them:

    python main.py --force                          # redo the whole grid from scratch
    python main.py --models cloud --samplings A --force   # redo one run
    python main.py --redo-failed                    # re-run only the failed documents (e.g. after a timeout)

`--redo-failed` re-runs only the documents that failed (timeout, truncated or invalid answer) and keeps all
successful rows, so it is much cheaper than `--force`. Use it after a transient error or after changing limits such
as `max_retries` or `max_tokens` in `config.yaml`. At `temperature: 0` a deterministic failure (for example a runaway
generation of a small local model) usually repeats, so a failed document may simply stay failed: that is a result,
it is counted in `% valid` and in the metrics.

If the local Ollama server is not running, the local model is skipped with a message. Output: `results/*.jsonl`
(raw answers), `results/metrics_*.json` (all metrics), `results/summary.csv`, `report/table.md`.

Single steps:

    python -m src.run --model cloud --sampling A --prompt v1   # --ids ID for one excerpt, --split dev for tuning
    python -m src.metrics results/<run>.jsonl                  # metrics on the golden split
    python -m src.eval                                         # results/summary.csv and report/table.md
