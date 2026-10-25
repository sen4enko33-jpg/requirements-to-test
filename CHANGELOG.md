# Prompt changelog

Prompts live in `prompts/extract_<version>.md`. The version is passed to `src/prompts.py` (`build_prompt("v1", text)`).
Each entry records what changed and why; results are added after the evaluation run.

## v1 (2026-10-14) — baseline

**What it is.** Minimal instruction prompt: role, task, seven general rules, the document placeholder. Field descriptions are not repeated here (they live in the schema). No examples, no edge-case handling.

**Design decisions.**
- Field descriptions live only in `Field(description=...)` in `src/schema.py`; the schema reaches the model through structured output (OpenAI-compatible `response_format` json_schema, used for both OpenRouter and Ollama). The prompt holds only what the schema cannot say: when to use null, what not to extract, copy-as-is rules.
- `text` of a requirement is copied from the source exactly as written, including typos; only layout artifacts (numbering, page headers, line breaks) are removed. The golden set keeps source typos in requirement text for the same reason.
- `open_questions` accepts only items the text itself marks as unresolved; `has_acceptance_criteria` is true only for explicit acceptance criteria.
- One requirement per complete statement; a list under a single "shall" stays one requirement.

**Known gaps (expected, not yet measured).** Granularity of use-case steps and event lists, handling of "Intentionally deleted" items and assumptions, `section` building when headings are partly cut off, ids given at section level, and sentences inserted in another language. These are the candidates for v2.

**Results.** Golden set: 10 excerpts, 158 requirements; every configuration ran on all 31 excerpts. Full run report: `report/report_v1.md`; table: `report/table.md`; all metrics: `results/summary.csv`.

| model | sampling | valid | req. P / R / F1 | domain | actors F1 | type | testable | section | latency p50 / p95 | $ per 1000 docs |
|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-4o-mini | A | 100% | 0.61 / 0.69 / 0.64 | 90% | 85% | 58% | 58% | 13% | 8.1 / 15.5 s | 0.76 |
| openai/gpt-4o-mini | B | 100% | 0.57 / 0.66 / 0.61 | 90% | 85% | 51% | 55% | 6% | 7.7 / 14.2 s | 0.75 |
| llama3.2:3b | A | 81% | 0.23 / 0.19 / 0.21 | 10% | 58% | 13% | 16% | 3% | 21.8 / 45.5 s | 0 |
| llama3.2:3b | B | 84% | 0.44 / 0.31 / 0.36 | 30% | 55% | 17% | 19% | 0% | 23.1 / 72.3 s | 0 |

Field accuracies are strict (a requirement that was not found counts as wrong); latency covers successful answers only; the local cost ignores hardware and electricity.

**Observations (v1 only).**
- `section` almost never matches: models return only the nearest heading (or a section number) although the schema asks for "parent > nearest". Main target for v2.
- The local model falls into runaway repetition on excerpts with near-identical sentences: 6 (A) and 5 (B) of 31 excerpts hit the token limit and failed, 4 (A) and 3 (B) more returned valid JSON with no requirements. At temperature 0 the loop repeats; B (t=0.7) is better than A for the local model, the opposite of the cloud model.
- The cloud model sometimes paraphrases instead of copying (use-case style lists, e.g. 0000_gamma_j_2) and returns extra requirements (57 unmatched in A); both break the copy-as-is rule.
- Candidate v2 rules: do not repeat a requirement that was already listed and stop when the excerpt ends; build `section` from the full heading path. They must be derived from errors on the dev split, not from golden.

**Notes on the evaluation.**
- Requirements are paired by text similarity >= 0.75 and >= 70% shared words. Sensitivity check: 109-110 of 158 matches for cloud A for any similarity threshold between 0.6 and 0.85; looser settings mostly add paraphrases. A paraphrase counts as a miss by design.
- Local limits `max_retries: 1`, `max_tokens: 4096` were set during the run, after four documents of run A had timed out three times; the failed rows were re-run with `--redo-failed`. All successful rows of run A (max 2338 tokens) are below the new limit. In run B one successful answer used 4040 of 4096 tokens, so the limit is tight and a long legitimate answer may be cut.
- Prices: openai/gpt-4o-mini via OpenRouter, $0.15 / $0.60 per 1M tokens; provider-reported cost matched (A exactly, B about 10% lower).
- Ten golden excerpts are a small sample: differences of a few points are noise, the gap between the cloud and the local model is not.

<!-- Template for the next entry:

## v2 (date)

**What changed.** ...
**Why.** (which errors from the error analysis it targets)
**Results vs v1.** ...
-->
