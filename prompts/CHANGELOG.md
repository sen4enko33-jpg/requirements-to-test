# Prompt changelog

Prompts live in `prompts/extract_<version>.md`. The version is passed to `src/prompts.py` (`build_prompt("v1", text)`).
Each entry records what changed and why; results are added after the evaluation run.

## v1 (2026-10-14) — baseline

**What it is.** Minimal instruction prompt: role, task, seven general rules, the document placeholder. Field descriptions are not repeated here (they live in the schema). No examples, no edge-case handling.

**Design decisions.**
- Field descriptions live only in `Field(description=...)` in `src/schema.py`; the schema reaches the model through structured output (OpenAI-compatible `response_format` json_schema, used for both OpenRouter and Ollama). The prompt holds only what the schema cannot say: when to use null, what not to extract, copy-as-is rules. *(Correction of 2026-10-27: this holds for the cloud model only. Ollama turns the schema into an output grammar and does not pass the descriptions to the model, so llama never saw them; see "v3" below.)*
- `text` of a requirement is copied from the source exactly as written, including typos; only layout artifacts (numbering, page headers, line breaks) are removed. The golden set keeps source typos in requirement text for the same reason.
- `open_questions` accepts only items the text itself marks as unresolved; `has_acceptance_criteria` is true only for explicit acceptance criteria.
- One requirement per complete statement; a list under a single "shall" stays one requirement.

**Known gaps (expected, not yet measured).** Granularity of use-case steps and event lists, handling of "Intentionally deleted" items and assumptions, `section` building when headings are partly cut off, ids given at section level, and sentences inserted in another language. These are the candidates for v2.

**Results.** Golden set: 10 excerpts, 158 requirements; every configuration ran on all 31 excerpts. Final report: `REPORT.md`; table: `report/table.md`; all metrics: `results/summary.csv`.

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

## v2 (2026-10-25) — fixes found on the dev split

**What changed.** Two rules added after rule 7 of v1 (rules 1–7 are word for word the same); the schema is unchanged, so v1 and v2 differ only in the prompt (true for all runs up to 2026-10-26; see "v3" for the later reword of the `section` description).
- 8. `section` is built from heading titles only, never a bare number, with one example.
- 9. Each requirement is listed once; stop at the end of the excerpt; statements that differ in one detail are different requirements.

**Why.** Errors found by reading the answers of v1 on the 11 dev excerpts (6 documents; no labels, the golden set was not used), counted over all four v1 runs.
- `section` is often a bare number although the schema forbids it: 39% of gpt-4o-mini requirements (66 of 168), 54% of llama A (60 of 112), 87% of llama B (163 of 187); a " > " path is in 20% of the gpt-4o-mini sections and never in llama's.
- llama repeats itself: exact duplicate requirements in 35 of 187 (B) and 2 of 112 (A); one excerpt gave 45 near-identical constraints. gpt-4o-mini has no duplicates.
- Also seen, handled in the first iteration and then dropped (see below): `domain` is `space` for 7 of 9 valid llama documents although one dev document is about space; llama B invented the title "Document Title".

**Iterations on dev.** Rules were tested on dev only (cloud A and local B, one run each, so differences of a few points are noise, especially for llama B at temperature 0.7).
1. Rules 8–11 (11: `doc_title` only if printed, 10: `domain` by purpose, `space` only for space systems). gpt-4o-mini: bare-number sections 66 → 0, but every document became `other` (gaia_1 `space` → `other`, probably wrong) and the same total of requirements (168) shifted: znix_2 13 → 19, peazip_1 15 → 22 (descriptive sentences), peazip_2 19 → 7 (several statements merged into one). The phrase "and are all kept" in rule 9 was suspected of pushing the model to extract more; it was removed.
2. Rules 8–11 again, rule 10 reworded. gpt-4o-mini run and one llama run were discarded: the prompt file started with a stray line of text pasted by mistake (the runs are kept as `results/experiments/dev_iter2_contaminated_*` for reference). The clean llama B run: bare-number sections 163 of 187 → 0 of 118, but `domain` = `space` for 10 of 10 documents (naming `space` in the prompt seems to push the small model to it) and `doc_title` filled for 10 of 10 (page headers such as "Software Requirements Specification" instead of null).
3. Rules 8–9 only (final). Rules 10 and 11 were dropped: no benefit for gpt-4o-mini, and they made llama worse; without them `doc_title` and `domain` return to v1 behaviour. Final dev numbers, v1 → v2:

| dev (11 excerpts) | gpt-4o-mini A | llama B |
|---|---|---|
| `section` as bare number | 66 → 0 | 163 of 187 → 2 of 142 |
| `section` as " > " path | 34 → 109 of 185 | 0 → 35 of 142 |
| requirement text found verbatim in the source | 95% → 96% | 80% → 94% |
| duplicate requirements | 0 → 0 | 35 (19%) → 19 (13%) |
| no usable answer (failed or empty) | 0 → 0 | 3 → 3 |
| latency p50 | 10.2 → 9.5 s | 32.8 → 14.5 s |

**Design decisions.**
- Rule 8 repeats what the schema description of `section` already says. This is a deliberate exception to "describe a field once, in the schema": gpt-4o-mini often ignored the schema text and llama never received it (see "v3" below), so v2 adds an explicit rule with an example. The schema stays untouched to keep the v1/v2 comparison clean (until 2026-10-27: the `section` description was reworded later, see "v3").
- Not changed: `id`, `type`, `testable` (no labels on dev, so it cannot be said whether leaving `id` empty in 79% of requirements or labelling almost everything `functional` / `yes` is an error); empty and truncated local answers (a rule would be a guess; the loop fix is described in "Local-model loops" below).

**Known weaknesses of v2 (from dev).**
- Rule 9 has no measurable effect on duplicates or truncated answers; it is kept because it is harmless for gpt-4o-mini and targets a documented failure of llama.
- gpt-4o-mini adds descriptive sentences that are not requirements in some documents (znix_2 13 → 19, peazip_1 15 → 22) and sometimes merges a whole list into one long requirement (peazip_2).
- llama's `domain` stays unreliable and cannot be fixed by the prompt.
- At temperature 0.7 a single llama run varies a lot (peazip_1: 10 → 40 requirements, truncated answers 0–2 per run).

**Results vs v1.** gpt-4o-mini on the golden set (10 excerpts), sampling A: section strict 9% → 20%, last heading 54% → 60%; req. F1 0.65 → 0.65 (P 0.61 → 0.58, R 0.69 → 0.73). Cost: partial 0% → 13%, $0.80 → $0.99 per 1000 docs. llama3.2:3b, sampling A: req. F1 0.24 → 0.30, section last heading 6% → 14%, partial 19% → 48%. Differences in F1 are within noise (10 documents, one run); see REPORT.md.

## Local-model loops (2026-10-26) — array limits, not a prompt change

**Problem.** Lecturer feedback: long excerpts make the local model loop. llama3.2:3b sometimes gives no answer: the output is cut at max_tokens (4096) after ~90 s. On the 21 excerpts outside the golden set (dev + excluded) 9 had a truncated or empty local answer in the v1 A/B runs.

**Diagnosis** (dev + excluded only, golden not used).
- Length is not the cause: mean 4288 characters for the failing documents and 4409 for the others. They have more lines (55 vs 34) and more short lines (70% vs 47%), i.e. table-like layout; weak signal (9 vs 12 documents).
- The raw output of library_2 shows the model looping inside JSON arrays, in two places: first `actors` ("system administrators" thousands of times, 0 requirements printed), and, once `actors` was limited, `requirements` (86–142 objects with only 4–18 distinct statements, plus table labels such as "Source: ITS", "Priority: 3", "Page 6" taken as requirements). The strict JSON grammar does not let the model close an array early.

**Tried and rejected** (dev, llama, A, v2, one run each).
- `frequency_penalty` 0.3 on whole documents: 1 of 5 documents that failed before recovered (gaia_2); the others were cut at 4096 tokens again. The penalty is too weak against a repeated short token, and a stronger one also hits the JSON structure tokens.
- Chunk fallback (pieces of ~1800 characters answered separately, merged, repeats dropped; used only for failed documents): all 3 failed dev documents got an answer, but 2 of 3 chunks of library_2 still looped, runs took up to 268 s instead of ~90 s, and quality was mixed (library_2 6 requirements, gaia_2 24, peazip_2 25 without violations). The code was removed to keep the pipeline simple.

**Adopted.**
- `schema_limits` for the local model in `config.yaml`: `maxItems` on `actors` 10, `open_questions` 10, `requirements` 40, added to the schema of the request only; the Pydantic schema, the validation and the cloud model are unchanged. 40 comes from the token budget (~60 tokens per requirement) and from dev (at most 32 requirements in a valid answer); it was not tuned on the golden set.
- Exact repeats (same words) inside one answer are dropped before the copy check; the number is logged as `n_duplicates_removed`.
- `requirements_capped` marks an answer that reached the requirements limit (looped or cut short, possibly incomplete); metrics `n_capped`, `capped_pct`, `n_duplicates_removed`.
- `schema_limits` is logged in every row; a log file never mixes rows made with different limits (`--force` starts over).

**Result on dev** (llama A v2, requirements / status, `v` = copy violations).

| document | no limits | limits |
|---|---|---|
| library_2 | failed | 13, partial (v3) |
| gaia_2 | failed | 28, partial (v2) |
| peazip_2 | failed | 18, partial (v9) |
| znix_2 | 16, partial (v1) | 17, ok |
| other 7 documents | same | same |

Failed documents 3 → 0, no call took the 90 s cut-off. Repeats removed: library_2 27, znix_2 23, peazip_2 22, gaia_2 5; `capped`: library_2, znix_2, peazip_2.

**Limits of the fix.**
- Answers that looped keep lower quality: peazip_2 has 9 of 18 requirements not copied.
- An empty answer without a loop (agentmom_1: 0 requirements in every dev run) is not affected; it shows up in `empty_pct`.
- Layout fragments taken as requirements ("Page 6", "Related Process") stay; a candidate for the error analysis and the next prompt version.
- The limit of 40 can cut a legitimately long list; `requirements_capped` shows where it was reached.
- Local logs of v1 and v2 made without limits are not comparable with new ones: both versions are re-run with the limits before the final table.
- One run at sampling A; sampling B was not tested.

## v3 (2026-10-27) — tried and rejected: field definitions in the prompt

**Why.** Review of the `section` definition (lecturer feedback, point 3). The schema description of `section` was reworded: at most two levels, one title if there is no parent heading, `null` if no heading is printed above the requirement. Comparing dev runs of v2 before and after the reword showed that for llama nothing changed: the same requirements and sections in all 11 documents and the same number of input tokens. For gpt-4o-mini the input grew by about 30 tokens per document. Ollama uses the schema only as an output grammar and does not pass the descriptions to the model, so in v1 and v2 llama never saw any field description (`type`, `testable`, `domain`, `id`, `open_questions`, ...); only the prompt text reaches it. For gpt-4o-mini the effect of the reworded `section` description was small (paths with 3 levels 3 → 3, `null` 14 → 15 of about 185 requirements).

**What changed.** v3 = v2 plus a "Field definitions" block that repeats the schema descriptions word for word (`tests/test_prompt_defs.py` checks it), the sentence that pointed to the schema replaced, and rules 5 and 8 aligned with the new `section` definition. The values of `domain` are not listed (naming `space` earlier pushed llama to it).

**Result on dev** (sampling A, 11 excerpts, v2 → v3). There are no labels on dev, so only signals that need no labels.

| | gpt-4o-mini | llama |
|---|---|---|
| status | 11 ok → 11 ok | 7 ok, 4 partial → 3 ok, 8 partial |
| requirements | 182 → 159 | 151 → 263 |
| copy violations | 0 → 0 | 15 → 39 |
| `id` filled / found in the excerpt | 34 / 34 → 33 / 33 | 59 / 53 → 255 / 26 |
| run time of the 11 excerpts | 131 → 150 s | 590 → 1138 s |

- llama invented identifiers: the description of `id` has the example 'REQ-12' and llama filled `REQ-1`, `REQ-3`, ... in 255 requirements, only 26 of the ids are in the text.
- llama went back to extracting headings and diagram labels (agentmom_1 0 → 39 requirements, among them "3.2.1 Unicast Communication" as a constraint; 22 of 39 not copied) and gave 4–8 times more requirements for peazip_1, znix_1, library_1. Probable cause, not tested separately: the wording "All requirements found in the excerpt" and the examples in the definitions.
- `type` shifted strongly (llama: constraint 10 → 107 of 263); whether it is more correct cannot be said without labels.
- gpt-4o-mini: no breakage, fewer requirements, more diverse `type`; whether this is better is for the golden evaluation.

**Decision.** v3 is rejected and was not evaluated on the golden set; `prompts/extract_v3.md` stays as a record. The final comparison is v1 against v2. Not tried: definitions of only `type` and `testable` without examples.

**Consequences.**
- Field descriptions in the schema work only for the cloud model; the claims in the v1 entry and in the README are corrected.
- The model comparison has this difference built in: gpt-4o-mini sees the definitions of `type` and `testable`, llama does not. It goes into the limitations of the report.
- The `section` description was reworded on 2026-10-27, after the v1 golden runs and the v2 dev iterations. v1 and v2 are re-run with the new schema (and the array limits) before the final table; earlier v1 numbers are history.
- Moving a definition into the prompt can backfire on a small model (the same effect as naming `space`): examples are copied.
