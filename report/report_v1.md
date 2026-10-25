# Run report — prompt v1 (baseline)

Steps 1–2 of the capstone: structured extraction of requirements with a cloud and a local model, same schema, same prompt, two sampling configs. Quality is measured on the golden set only. Error analysis and the production recommendation are not part of this report (steps 3–4).

## 1. Setup

| item | value |
|---|---|
| Cloud model | `openai/gpt-4o-mini` via OpenRouter, $0.15 / $0.60 per 1M tokens (input / output) |
| Local model | `llama3.2:3b` via Ollama, server started with `OLLAMA_CONTEXT_LENGTH=8192` |
| Interface | one OpenAI-compatible client for both; structured output (`response_format` json_schema, strict) |
| Sampling A | temperature 0.0, top_p 1.0 |
| Sampling B | temperature 0.7, top_p 0.9 |
| Prompt | `prompts/extract_v1.md` (see `CHANGELOG.md`) |
| Input | 31 noisy excerpts (`data/noisy`): 10 golden, 11 dev, 10 excluded (siblings of golden documents) |
| Scored on | 10 golden excerpts, 158 gold requirements |
| Runs | 2 models × 2 samplings × prompt v1 = 4 runs, 31 excerpts each |
| Retry / limits | cloud: timeout 60 s, 3 retries, max_tokens 8192; local: timeout 120 s, 1 retry, max_tokens 4096 |

Reproduce: `python main.py` (`--force` to start from scratch, `--redo-failed` to re-run only failed rows). Raw outputs are in `results/*.jsonl`, metrics in `results/metrics_*.json` and `results/summary.csv`.

## 2. Main results

| model | sampling | valid | doc_title | domain | language | acceptance | actors F1 | type | testable | id | section | p50 / p95 | $ / 1000 docs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-4o-mini | A | 100% | 50% | 90% | 90% | 100% | 85% | 58% | 58% | 59% | 13% | 8.1 / 15.5 s | 0.76 |
| gpt-4o-mini | B | 100% | 50% | 90% | 90% | 100% | 85% | 51% | 55% | 58% | 6% | 7.7 / 14.2 s | 0.75 |
| llama3.2:3b | A | 81% | 50% | 10% | 60% | 40% | 58% | 13% | 16% | 15% | 3% | 21.8 / 45.5 s | 0 |
| llama3.2:3b | B | 84% | 40% | 30% | 60% | 60% | 55% | 17% | 19% | 20% | 0% | 23.1 / 72.3 s | 0 |

- `doc_title`, `domain`, `language`, `acceptance`: exact match per document (10 documents). `actors`: F1 after fuzzy one-to-one matching (similarity ≥ 0.80).
- `type`, `testable`, `id`, `section` are **strict**: the denominator is all 158 gold requirements, so a requirement that was not found counts as wrong. Failed documents count as zeros.
- Latency: p50 / p95 over successful responses, retries included. Cost: tokens × configured prices, which matches the provider-reported cost (A exactly, B about 10% lower). Local cost is 0 and ignores hardware and electricity.

## 3. Requirement extraction

| model | sampling | precision | recall | F1 | matched | merged | split | missed | extra |
|---|---|---|---|---|---|---|---|---|---|
| gpt-4o-mini | A | 0.61 | 0.69 | 0.64 | 109 | 5 | 3 | 28 | 57 |
| gpt-4o-mini | B | 0.57 | 0.66 | 0.61 | 104 | 6 | 3 | 31 | 64 |
| llama3.2:3b | A | 0.23 | 0.19 | 0.21 | 30 | 25 | 0 | 65 | 73 |
| llama3.2:3b | B | 0.44 | 0.31 | 0.36 | 49 | 10 | 0 | 87 | 52 |

Micro-averaged over all golden documents. merged / split / missed / extra are diagnostics of how predictions differ from the gold list (one prediction covering several gold items, one gold item cut into several predictions, gold items without any prediction, predictions without a gold item).

Field accuracy on matched requirements only (how right the model is when it finds the requirement):

| model | sampling | type | testable | id | section |
|---|---|---|---|---|---|
| gpt-4o-mini | A | 83% | 84% | 86% | 19% |
| gpt-4o-mini | B | 78% | 84% | 88% | 10% |
| llama3.2:3b | A | 67% | 83% | 77% | 13% |
| llama3.2:3b | B | 55% | 61% | 65% | 0% |

The local figures rest on few matches (30 and 49), so they are noisy.

## 4. Reliability

| model | sampling | failed | empty answer | valid JSON | latency p95, incl. failed |
|---|---|---|---|---|---|
| gpt-4o-mini | A | 0 / 31 | 0 | 100% | 15.5 s |
| gpt-4o-mini | B | 0 / 31 | 0 | 100% | 14.2 s |
| llama3.2:3b | A | 6 / 31 | 4 | 81% | 87.0 s |
| llama3.2:3b | B | 5 / 31 | 3 | 84% | 89.0 s |

- All local failures are `truncated: max_tokens reached`: the model keeps generating (runaway repetition on excerpts with near-identical sentences) until the 4096-token cap, about 87 s per document. "Empty" means valid JSON with zero requirements (about 3 s).
- On the golden set, 3 of 10 documents were lost in each local run (A: 2 failed + 1 empty; B: 1 failed + 2 empty).
- The cap is tight for run B: one successful answer used 4040 of 4096 tokens (next largest 3691). A long legitimate answer may therefore be cut and counted as a failure. In run A the largest successful answer was 2338 tokens.
- The local limits (`max_retries: 1`, `max_tokens: 4096`) were introduced during the run, after four documents of run A had timed out three times (363 s each). The failed rows were re-run with `--redo-failed`; successful rows were kept.
- Token counts are not comparable between models: OpenAI counts the JSON schema as prompt tokens, Ollama applies it as a grammar.

## 5. Observations

- `section` is almost never correct for either model (best 13% strict). The schema asks for "parent > nearest heading"; models return the nearest heading or only a number.
- The cloud model is stable at temperature 0 and slightly worse at 0.7 (F1 0.64 vs 0.61). The local model is the opposite: randomness (B) breaks some repetition loops and gives F1 0.36 vs 0.21 for A.
- The cloud model sometimes paraphrases instead of copying (list-style use-case documents) and over-extracts (57 predictions without a gold match). `doc_title` is correct in only 50% of cases for both models.
- The local model mostly gets `domain` wrong (10–30%), puts generic entries into `actors`, and labels most requirements with the same `type` / `testable` values.
- Cost and speed: the cloud model is about 3× faster at p50 and costs about $0.76 per 1000 documents; the local model costs nothing per call but is slower and unreliable on repetitive texts.

## 6. Limitations

- Ten golden documents (158 requirements) is a small sample: differences of a few points between configurations are noise; the gap between cloud and local is not.
- Matching of requirements is by text similarity ≥ 0.75 and ≥ 70% shared words. For cloud A the result is stable (109–110 matches) for any similarity threshold between 0.6 and 0.85; looser settings mostly add paraphrases. A paraphrase counts as a miss by design, because the prompt requires copying. A semantic matcher would give a higher recall (up to about 0.75 for cloud A).
- `open_questions` is stored but not scored in the main table (gold 10, predicted 7 / 7 / 2 / 1 in the order of the table rows).
- One prompt version; error analysis and prompt v2 come in steps 3–4.

## 7. Data attribution

Source documents come from the PURE dataset (https://zenodo.org/records/1414117), licensed CC BY 4.0. Excerpts were selected, noised and hand-labelled for this project.
