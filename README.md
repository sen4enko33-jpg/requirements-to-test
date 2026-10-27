# requirements-to-test

Extract structured requirements from messy text excerpts (taken from the PURE requirements
documents) using a schema, and compare a paid cloud model with a local model:
field-level accuracy, response validity, latency, and cost. The comparison report is in [`REPORT.md`](REPORT.md).

## Quick start
Python 3.11+.

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env      # put your OPENROUTER_API_KEY into .env (needed only to re-run the cloud model)
    python main.py

`python main.py` runs every model x sampling x prompt version from `config.yaml` (2 x 2 x 2 = 8 runs over the 31
excerpts), writes the logs to `results/`, computes the metrics on the golden set and prints the comparison table
(also saved to `report/table.md`). Finished documents are skipped, so on the results that are committed here it
takes seconds and costs nothing. A model that cannot be reached (no API key, Ollama not running) is skipped and its
committed results are used. To redo everything from scratch use `python main.py --force`: the cloud runs cost about
$0.15 in total, the local model needs about two hours on a laptop and the setup described under Setup.

## Structure
- `data/texts` — clean text excerpts cut from the PDFs (31 files)
- `data/noisy` — the same excerpts with injected noise (typos, dropped sentences, Ukrainian sentences); these are the model inputs
- `data/golden` — manually labeled ground truth for 10 of the texts (`golden_ids.txt` lists them)
- `data/index.csv`, `data/noise_log.csv` — excerpt metadata and the log of injected noise
- `data/splits.json` — golden / dev / excluded split of the excerpts (built by `make_splits.py`)
- `src/schema.py` — Pydantic schema of the extraction result
- `src/prompts.py` — loads a prompt version and inserts the document text
- `src/clients/` — model clients behind one interface (`base.py`); `openai_compat.py` serves both OpenRouter and Ollama
- `main.py` — one-command entry point: all runs, metrics, table
- `src/run.py` — runs a model x sampling x prompt over the excerpts and writes `results/*.jsonl`
- `src/metrics.py`, `src/eval.py` — metrics per run and the comparison table
- `config.yaml` — models, prices, timeouts, sampling configs
- `prompts/` — prompt versions (`extract_v1.md`, …)
- `prompts/CHANGELOG.md` — what changed between prompt versions and why
- `results/` — logs of the 8 main runs (`<model>_<sampling>_<prompt>.jsonl`), their metrics (`metrics_*.json`) and `summary.csv`; `results/experiments/` — logs of the dev experiments behind `prompts/CHANGELOG.md` (not part of the final comparison)
- `REPORT.md` — the comparison report; `report/table.md` — the generated table
- `tests/` — checks with a fake model client, no API calls: `python tests/test_repair.py`, `python tests/test_limits.py`, `python tests/test_prompt_defs.py`

## Data source
The excerpts come from the PURE dataset of public software requirements documents (79 PDFs):
https://zenodo.org/records/1414117, licensed CC BY 4.0. The PDFs are not included in this repository.
`data/texts` holds excerpts cut from them, `data/noisy` the same excerpts with artificial noise added by
`add_noise.py`, `data/golden` the annotations written by hand. The excerpts and annotations are shared under the
same license, with attribution to the original dataset.

## Setup
Python 3.11+.

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
justified by dev errors only (see `prompts/CHANGELOG.md`).

    python make_splits.py

## Schema
`Extraction` (`src/schema.py`): `doc_title`, `domain` (enum), `language` (enum), `actors` (list),
`requirements` (list of `Requirement`: `id`, `section`, `text`, `type`, `testable`),
`has_acceptance_criteria`, `open_questions`. Field descriptions live in the schema (`Field(description=...)`). They reach a cloud model through structured output; the local model (Ollama) gets the schema only as an output grammar, not its text, so everything it must know has to be in the prompt (see `prompts/CHANGELOG.md`, v3).

## Prompts
Build a prompt for a document:

    from src.prompts import build_prompt
    prompt = build_prompt("v1", document_text)

Versions and their rationale are in `prompts/CHANGELOG.md`.

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
successful rows (documents with status `partial_failed` have an answer and are kept too), so it is much cheaper than `--force`. Use it after a transient error or after changing limits such
as `max_retries` or `max_tokens` in `config.yaml`. At `temperature: 0` a deterministic failure (for example a runaway
generation of a small local model) usually repeats, so a failed document may simply stay failed: that is a result,
it is counted as not valid in `% valid` and in the metrics.

If the local Ollama server is not running, the local model is skipped with a message. Output: `results/*.jsonl`
(raw answers), `results/metrics_*.json` (all metrics), `results/summary.csv`, `report/table.md`.

Single steps:

    python -m src.run --model cloud --sampling A --prompt v1   # --ids ID for one excerpt, --split dev for tuning
    python -m src.metrics results/<run>.jsonl                  # metrics on the golden split
    python -m src.eval                                         # results/summary.csv and report/table.md

## Validation and repair
Every model answer is checked twice (`src/validate.py`):

1. **Schema.** The answer must be valid JSON that matches the `Extraction` schema.
2. **Copy check.** Every requirement `text` must be copied from the excerpt, as the prompt demands. Layout that the
   prompt allows to remove (bullets, list numbers, case, line-break hyphens, and page headers and footers) is
   ignored. A requirement passes if its words occur in the excerpt as one run, or if at least 95% of them are found
   and the found pieces lie within 15 excerpt words of each other (`COPY_MIN_COVERAGE`, `COPY_MAX_GAP`). The check
   does not see two neighbouring statements merged into one, because every word of such a text is real.

If either check fails, the model gets **one repair attempt**: the same prompt plus its previous answer and the list of
errors (for a copy error: which requirement and which words are not in the text), with the same sampling parameters.
A repaired answer that fixes a schema error is accepted if it is valid. A repaired answer of an already valid answer
is accepted only if it has no more copy violations and no fewer correctly copied requirements than the first one, so
"fixing" an answer by dropping good requirements (or returning an empty list) does not count. There is never a third
call. Answers that never arrived (timeout, `max_tokens` reached, refusal) are not repaired: there is nothing
to fix, and for a runaway generation a repeat would only cost another minute and a half.

Status of a document:

- `ok`: a valid answer, every requirement copied.
- `partial_failed`: a valid answer, but some requirements are still not copied after the repair. The document keeps
  its answer and is scored normally; the number of such requirements is in `copy_violations`.
- `failed`: no valid answer.

Each row of `results/*.jsonl` logs the model, the prompt version, the sampling name and values, `repair_attempted`,
`repaired` (the repaired answer was accepted), `repair_reason` (`schema` or `copy`), `validation_errors` and
`copy_errors_first` (the errors of the first answer), `copy_violations` and `copy_total` (not copied requirements and
all requirements in the accepted answer). The metrics report `valid_pct` (a valid answer exists: `ok` +
`partial_failed`), `partial_failed_pct`, `valid_first_try_pct`, `n_repair_attempted`, `n_repaired`,
`copy_violation_pct` (share of requirements that are not copied) and `copy_violation_pct_first_try` (the same before
the repair, which shows what the repair gives). Copy metrics are recomputed from the answers, so they also work on old
run logs. With strict structured output invalid JSON is rare, so the repair paths are covered by a test with a fake
client: `python tests/test_repair.py` (validation, copy check, repair), `python tests/test_limits.py` (array limits, repeats, capped flag).

### Loops of the local model

The local model sometimes loops inside a JSON array until `max_tokens`. For it, `config.yaml` sets `schema_limits` (`maxItems` in the request schema: actors 10, open_questions 10, requirements 40); validation uses the unchanged Pydantic schema. Exact repeats inside one answer are dropped (`n_duplicates_removed`), and an answer that reaches the requirements limit is marked `requirements_capped` (`capped_pct` in the metrics). A log file does not mix rows made with different limits (`--force`). Evidence and rejected alternatives (repetition penalty, chunking) are in `prompts/CHANGELOG.md`.
