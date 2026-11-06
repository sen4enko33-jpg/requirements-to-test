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
- `rag/` — the RAG part of the project (corpus, ingestion, chunking, later search and answering); see "RAG: corpus and ingestion" and "RAG: chunking" below
- `tests/test_answer.py` — checks of the answering step (context budget, prompt, citation checks, "I don't know" paths) with a fake search and a fake model (no network)
- `tests/test_retrieval.py`, `tests/test_retrieval_eval.py` — checks of the search (filters, RRF, reranking, index resume) and of the retrieval metrics, with a fake embedding model and Chroma in memory (no network)
- `tests/test_chunking.py` — checks of the chunking: size limits, no lost text, headings, overlap, tables, chunk metadata (no API calls)
- `tests/test_ingest.py`, `tests/test_ingest_pipeline.py` — checks of the ingestion cleaning, OCR rule, duplicate detection and manifest (no API calls)

## Data source
The excerpts come from the PURE dataset of public software requirements documents (79 documents, mostly PDF, some DOC,
HTML and RTF): https://zenodo.org/records/1414117, licensed CC BY 4.0. The original files are not included in this
repository, except the 40 that the RAG part uses (`rag/data/raw/`, see "RAG: corpus and ingestion").
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

## RAG: corpus and ingestion

The RAG part works on 42 documents: 40 requirements documents of the PURE dataset (26 PDF, 10 DOC, 3 HTML, 1 RTF, CC BY 4.0), one sample company policy (`remote_work_policy.pdf`, supplied by the author, not part of PURE) and an older, fictional version of the same policy (`remote_work_policy_2023.pdf`). The older version was written for this project (`rag/tools/make_policy_2023.py`) because the PURE files contain no document in two versions; it has the same sections as the 2026 policy but different facts (three remote days instead of two, 25 EUR instead of 40, 24 hours instead of one hour, other core hours, personal computers allowed with approval), and it is the test case for questions about outdated versions. `rag/corpus.yaml` lists them with the reason each one is in the corpus (for example, similar or versioned documents for the trap questions of the test set); the originals are in `rag/data/raw/`.

    python -m rag.ingest.cli            # raw files -> rag/data/processed/*.md + rag/data/manifest.json
    python -m rag.ingest.cli --force    # process everything again (--ids a b: only these documents)

Unchanged files are not processed again: the manifest stores the hash of every raw file and of the ingestion code. The cleaned documents and the manifest are committed, so the next steps do not need the tools below.

**What ingestion does** (`rag/ingest/`):

- *Extraction to Markdown with the structure kept.* PDF (PyMuPDF): headings from font size and section numbers, bullets as `- `, a `<!-- page N -->` marker before each page (for citing pages). DOC and RTF are converted to DOCX by LibreOffice, then `Title` becomes `# `, `Heading N` becomes N+1 hashes, list paragraphs become `- ` (`List Number` becomes `1. `), tables become `| a | b |` rows. HTML (BeautifulSoup): `<main>` (else `<body>`), `h1`-`h6` become `#`-`######`, `li` becomes `- `, tables become rows; old pages without `h1`-`h6` use short all-bold paragraphs or list items as headings. Tables inside PDFs are not parsed, their text stays in reading order.
- *Scans.* A PDF page with no text layer (fewer than 80 characters) that is one big picture (at least 60% of the page) is a scan page; when most pages are scans, they are read with OCR (Tesseract, English; `RAG_OCR_LANG=eng+ukr` after installing the language pack) and then processed like any other PDF. A figure with little text in an otherwise digital PDF is not OCR-ed (OCR of a diagram is noise). If OCR is missing or finds nothing, the document gets the status `skipped_scanned` in the manifest.
- *Cleaning* (`clean.py`; every rule counts what it removed in the manifest): Unicode normalisation, U+FFFD and soft hyphens; running headers and footers (a line repeated at the top or bottom of at least 30% of the pages) and page numbers; tables of contents (also left-over lines with dot or underscore leaders such as `Scope ....... 3`); the navigation bar of HTML pages; paragraphs and hyphenated words cut by a line or page break; separator lines and single letters. A document gets a warning if the cleaning removed more than 25% of its words, has fewer than 300 words or has no headings.
- *Duplicates* (`dedup.py`): documents with the same normalised text are exact duplicates (the first is kept, the other gets the status `duplicate`). Documents that share many 5-word shingles (Jaccard of at least 0.3 or containment of at least 0.6) are only marked as `near_duplicates`, not removed: other versions of a document are what the trap questions need. Currently one pair is marked: `2005_clarus_high` and `2005_clarus_low` (74% of the smaller text is in the larger one).
- *Manifest* (`rag/data/manifest.json`): per document the title, year (from the file name), version and date (best effort, from the first page before the running header is removed), hashes of the raw file and of the cleaned text, page count, structure counts, cleaning statistics, warnings, status and duplicate information.

**Install.** `pip install -r requirements.txt` (PyMuPDF, python-docx, BeautifulSoup, lxml); LibreOffice (`soffice` on the PATH) is needed to read DOC and RTF; Tesseract is needed only for scans.

**Checks.** `python tests/test_ingest.py` (cleaning, OCR rule; the OCR checks are skipped when Tesseract is missing) and `python tests/test_ingest_pipeline.py` (duplicates, manifest, cache).

**Known limits.** Section headings of PDFs are detected heuristically: a numbered list item can look like a section and the first requirement id can stay in a heading. A scan is recognised only when most pages are scans. Lone letters such as the priority marks `H`/`L`/`M` of one document (`2005_clarus_low`) are removed by the cleaning as noise. The OCR language is English by default.

## RAG: chunking

    python -m rag.chunking.cli       # rag/data/processed/*.md -> rag/data/chunks.jsonl + rag/data/chunks_manifest.json
    python -m rag.chunking.compare   # structural vs fixed size -> rag/data/chunking_comparison.md (a report, not used later)

**Strategy `structural-v1`** (`rag/chunking/structural.py`). Requirements documents are written in numbered sections, and a question is usually answered by one requirement or one section. A chunk therefore follows the sections of the document instead of a fixed number of words:

- A document is split into blocks (heading, paragraph or list item, table) with the heading path and the page of each block.
- A chunk holds blocks of one section, about 300 words (target), at most 400 words and at most 480 tokens of the embedding model (an unsplittable block can be longer; this happens twice in the corpus). The token limit matters for code, logs and tables, which use up to 2.4 tokens per word (prose about 1.4); the embedding model `BAAI/bge-small-en-v1.5` reads only 512 tokens and silently drops the rest, and without the token limit 92 chunks (6%) would have been cut. The 32 tokens of margin are for headings and special tokens. A heading always stays with the text below it, never alone at the end of a chunk.
- A long section is cut between paragraphs. A continuation chunk starts with the last paragraph of the previous chunk (at most 60 words) as overlap, so a sentence that refers to the previous one keeps its context. Between two sections there is no overlap, because the neighbouring section is a different topic.
- A chunk of fewer than 60 words (a title page, a short section, the text of a diagram) is attached to the previous chunk of the document when the result is at most 400 words; the first chunk of a document is attached to the next one. Such a chunk can contain two sections; the field `sections` lists all of them. After this rule no chunk is shorter than 60 words.
- An oversized paragraph is cut between sentences, an oversized table between rows, with the header row repeated in every part. A single table row longer than the limit is not cut.

**Chunk metadata** (`chunks.jsonl`, one JSON object per line): `chunk_id` (`<doc_id>#0007`), `doc_id`, `source_file`, `title`, `section` (heading path of the first section, parts joined by ` > `), `section_path`, `sections`, `page_start`, `page_end` (PDF only), `year`, `version`, `date`, `doc_sha256` (hash of the cleaned document), `sha256` (hash of the chunk text), `n_words`, `n_tokens`, `overlap_words`, `position`, `n_chunks_in_doc`, `prev_id`, `next_id`, `text`. `prev_id` and `next_id` let the answering step add the neighbouring chunks. Duplicate documents are not chunked. `chunks_manifest.json` has the parameters (including the tokenizer), the code hash and per-document counts. The tokenizer is loaded through `rag/models.py` (the model files are cached in `rag/.cache/`, not in git; the first run downloads about 130 MB).

**Comparison with fixed size** (`chunking_comparison.md`). The baseline cuts the same documents into windows of 300 words with 15% overlap and ignores the structure. Both are measured with the same heuristics on the chunk text (42 documents):

| metric | structural-v1 | fixed 300 |
|---|---|---|
| chunks | 1669 | 1164 |
| size mean / median / max (words) | 180 / 179 / 496 | 296 / 300 / 300 |
| starts in the middle of a sentence | 4.3% | 63.8% |
| ends in the middle of a sentence | 9.0% | 49.1% |
| contains more than one section | 23.1% | 60.5% |
| chunks over 512 tokens (cut by the embedding model) | 2 | 124 |
| text beyond 512 tokens | 0.1% | 4.8% |

Fixed windows cut a sentence in about every second chunk and mix unrelated sections in most of them; the structural chunks start at a sentence in 96% of cases (the rest are mostly log lines that begin with a file name in lower case, which the heuristic counts as a cut). Fixed windows also exceed the 512 tokens of the model in 124 chunks, so about 5% of their text would never reach the embedding. The price is more and smaller chunks. Whether this also gives better search is measured in the retrieval step on the same labelled questions (recall@k and MRR for both chunkings); these numbers only show that the chunks are well formed. The file also lists, for four documents, a fixed chunk that cuts the text next to the structural chunk with the same beginning.

**Checks.** `python tests/test_chunking.py` (42 checks; the token limit is tested with a fake tokenizer, so no model is needed).

**Known limits.** The sentence metrics are heuristics (a list item or a label can look like a cut). Section boundaries are only as good as the heading detection of ingestion (see above). Some running headers of `2006_eirene_sys_15` ("PSA167D006-15 Page 115") stay in the text and in 9 chunks. One paragraph of `2004_ijis` has no punctuation and stays a chunk of 496 words. Two chunks stay above the token limit (a punctuation-free paragraph of `2004_ijis` and a very long table row of `2004_e_procurement`, 754 and 526 tokens); the embedding sees their first 512 tokens. A word count is not a token count: chunks of code and logs are short in words (the 30-word chunks of `2004_watcom` have 432 tokens).

## RAG: retrieval

    python -m rag.retrieval.build            # embed rag/data/chunks.jsonl into the Chroma collection chunks_structural
    python -m rag.chunking.cli --fixed       # the fixed-size baseline: rag/data/chunks_fixed.jsonl
    python -m rag.retrieval.build --fixed    # ... and its collection chunks_fixed
    python -m rag.eval.run_retrieval         # recall@k and MRR -> rag/data/retrieval_results.md (+ .json)

**Components** (`rag/retrieval/`, `rag/models.py`).

- *Embeddings:* `BAAI/bge-small-en-v1.5` (fastembed, local, 384 dimensions, 512-token limit; chunking keeps every chunk under it, see above). *Vector database:* Chroma, cosine distance, one collection per chunking; the metadata of the chunk (`doc_id`, `title`, `year`, `version`, `date`, `section`, ...) is stored next to the vector. The index is stored in `rag/data/chroma/` (not in git; override with `RAG_CHROMA_DIR`, SQLite does not work on a network drive). The build resumes after an interruption and rebuilds only when the chunks or the model change (`--max-seconds=N` stops early for short-lived shells).
- *BM25* (`rank_bm25`) over the section path and the text, with a simple tokenizer that keeps identifiers such as `REQ-33` whole.
- *Hybrid:* the vector ranking and the BM25 ranking (50 candidates each) are merged with reciprocal rank fusion (RRF, k=60): a chunk gets 1/(60+position) from each list. Only positions are used, so there are no weights to tune.
- *Reranking:* a cross-encoder (`Xenova/ms-marco-MiniLM-L-6-v2`) reads the question together with each of the 20 best fused chunks and re-orders them.
- *Metadata filters:* every mode takes `filters={"doc_id": ..., "year": ..., "version": ...}` (a value or a list of values; all fields must match). Vector search passes the filter to Chroma, BM25 applies it to its candidates. Tested in all three modes, including the choice between the 2026 and 2023 policy by `year`.

**Questions and metrics.** `rag/eval/retrieval_questions.jsonl` has 15 questions that were written from a verbatim quote of one document and checked by hand (one or two of each kind: plain, paraphrase, hard paraphrase without shared words, number, requirement identifier, table row, twin documents, old and current version of the policy). A retrieved chunk is relevant when it comes from the question's document and contains the quote, so the same questions measure both chunkings. *recall@k* is the share of questions that have a relevant chunk among the first k results; *MRR* is the mean of 1/rank of the first relevant chunk (0 when it is not in the top 10). The search configurations were fixed before the first run and were not tuned on these questions.

| chunking | search | recall@1 | recall@3 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|---|---|
| structural-v1 | vector | 0.47 | 0.67 | 0.73 | 0.87 | 0.60 |
| structural-v1 | hybrid | 0.53 | 0.87 | 0.87 | 0.87 | 0.68 |
| structural-v1 | hybrid + rerank | 0.67 | 0.80 | 0.93 | 0.93 | 0.76 |
| fixed-300 | vector | 0.33 | 0.53 | 0.67 | 0.93 | 0.49 |
| fixed-300 | hybrid | 0.53 | 0.80 | 0.93 | 1.00 | 0.69 |
| fixed-300 | hybrid + rerank | 0.60 | 0.93 | 1.00 | 1.00 | 0.78 |

The per-question ranks are in `rag/data/retrieval_results.md`.

**What the numbers say.** With 15 questions one question is 0.07, so only large differences count.

- Hybrid is clearly better than vector search alone (MRR 0.60 to 0.68 for structural, 0.49 to 0.69 for fixed), and the two kinds of questions behave as expected: requirement identifiers (`REQ-33`, `SRS295`) are missed by the vectors in the structural index (not in the top 10) and found by BM25 (ranks 4 and 1 in the fixed index, 2 for `SRS295` in the structural one), while a question with no shared words (`q05`) is the weakest for BM25.
- The reranker raises MRR in both chunkings (0.68 to 0.76 and 0.69 to 0.78) and recall@1 (0.53 to 0.67 and 0.53 to 0.60), but it also makes mistakes: for `q26` and `q13` it moved the correct chunk down.
- The structural and the fixed chunking are about equal in retrieval (MRR 0.76 and 0.78 with the best search). The structural chunking does not find more; its advantage is that the chunks are complete passages with a section label, which matters for the cited answers of the next step. Fixed windows reach recall@5 = 1.00 on this small set; a likely reason is that their chunks are about 60% larger (296 against 180 words on average) and contain more text around the quote, but this was not tested separately.
- *Old and current version.* Without a filter the search returns both policies (for `q26` ranks 1 and 2 are the 2026 and the 2023 chunk, after reranking they are swapped), because neither BM25 nor the vectors understand "current". A `year` or `version` filter restricts the search to one version (tested on synthetic data, not on these questions); choosing the newest version by default is the task of the answering step.

**Known limits.** Only 15 questions, all written by one person from the documents themselves. `section` of a chunk names its first section; a chunk that merged tiny sections also lists the others in `sections`, and the reranker sees only the text. A question that is a loose paraphrase of one sentence in a long chunk can lose to chunks that talk about the same topic in general terms (`q05`). Reranker and embeddings read at most 512 tokens.

## RAG: answering with citations

    python -m rag.answer.cli "How many remote days per week are allowed?" [--year 2023] [--doc ID] [--show-context]

`OPENROUTER_API_KEY` in `.env` (as in the first part); the model is `models.cloud` of `config.yaml` (`openai/gpt-4o-mini`, temperature 0). The index of the previous step must exist.

**Flow** (`rag/answer/generate.py`).

1. *Search:* hybrid + reranking, top 10, optional filters (`year`, `doc_id`, ...).
2. *Guard before the model:* when there are no hits, or the reranker score of the best chunk is below `MIN_SCORE`, the answer is "I don't know" and the model is **not called**.
3. *Context within a token budget* (`rag/answer/context.py`): the chunks are taken in rank order until 3000 tokens (counted with the tokenizer of the embedding model) are used; a chunk goes in whole or not at all, and a smaller chunk further down may still fit. Every passage has a header, for example `[2] Remote Work Policy (remote_work_policy), effective 2026-01-15, section: 5. Information security, page 2`, so the model sees the document, the section, the date and the page.
4. *Prompt* (`rag/prompts/answer_v1.md`, changelog in `rag/prompts/CHANGELOG.md`): answer only from the passages, every fact sentence ends with `[n]`, one fixed sentence for "I don't know", rules for versions (newest wins unless the question names a version or year), for similar documents and for copying numbers exactly. The model returns JSON `{"answer", "sources"}` (structured output); invalid JSON is repeated once.
5. *Checks by code* (`rag/answer/citations.py`): every `[n]` must be a passage of the context, otherwise the reference is dropped from the citations and the answer is marked with `invalid_reference` (the model invented a source); `sources` must match the references in the text; a fact sentence without a reference is reported. The result lists each citation as document, section, version or date, page.

**`MIN_SCORE` = -2.0** (`rag/answer/settings.py`). It was chosen on a separate set (`rag/eval/dev_questions.jsonl`: 5 questions with an answer, 6 without; the test set of the next step was not used). The best chunk of an answerable question scored from -1.47 to 9.01, of an unanswerable one from -11.05 to 3.19; the ranges overlap, so no threshold separates them. -2.0 removes only the clearly unrelated questions (3 of 6) and no answerable one; a question that is on topic but not covered (for example, vacation days in the policy) is left to the model's own "I don't know" (rule 2). Eleven questions are a small sample.

**Checks.** `python tests/test_answer.py` (30 checks, fake search and fake model).

**What a first run showed** (not an evaluation; the metrics come in the next step). With the real model the 2023 and 2026 policies are answered correctly when a year filter or a year in the question is given, "I don't know" works for an unrelated question (without a model call) and for a policy question that is not covered (by the model). Without a version in the question, the model gave both versions but named the older one first, although rule 4 asks for the newest version to lead; this is a known gap of `answer_v1`, to be measured in the next step.

**Known limits.** The code accepts any reference that exists in the context; whether the cited passage really supports the sentence is checked in the next step (faithfulness). Comparing dates (rule 4) is left to the model. The version is not part of the search: a question without a year returns chunks of every version.

Data: PURE requirements documents, CC BY 4.0 (https://zenodo.org/records/1414117). The sample policy `remote_work_policy.pdf` and its older version `remote_work_policy_2023.pdf` are fictional documents of a fictional company.
