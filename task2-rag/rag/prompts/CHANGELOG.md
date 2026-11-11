# RAG prompt changelog

Prompts live in `rag/prompts/answer_<version>.md` and are loaded by `rag/answer/prompts.py` (`build_prompt("v1", context, question)`).
Each entry records what changed and why, with the result on the 28-question test set (`rag/eval/testset.jsonl`; scorers + judge, details in `REPORT.md`).

## v1 (2026-11) - baseline

**What it is.** One instruction block with seven rules, the numbered passages (`<<CONTEXT>>`) and the question (`<<QUESTION>>`).
The answer is JSON `{"answer", "sources"}` (structured output, schema `RagAnswer` in `rag/answer/generate.py`).

**Design decisions.**
- Answer only from the passages; every sentence with a fact ends with `[n]`. The code checks the numbers (`rag/answer/citations.py`): a number that is not in the context is an error.
- "I don't know" has one exact sentence, so code and scorers can recognise it. A second, cheaper guard runs before the model: when the best reranker score is below `MIN_SCORE` the model is not called.
- Versions (rule 4): without a version or year in the question the newest version wins and the older one is mentioned. The search does not know which version is newer, so this is left to the model; the dates are in the passage headers.
- Different documents are different systems (rule 5): the corpus has pairs of similar documents.
- Numbers, names and identifiers are copied exactly (rule 6).

**Known gaps (expected, not yet measured).** The model can still cite a passage that does not support the sentence (a number that exists in the context is accepted by the code); step 4 checks this with the faithfulness check. Rule 4 asks the model to compare dates, which a small model may do badly.

**First observation (one manual run, not a measurement).** For "How many days a week are employees allowed to work from home?" (no version in the question) the model returned both policies but put the 2023 value (three days) before the 2026 value (two days), against rule 4. With a year in the question or a `year` filter the answer was correct. Not fixed in v1 on purpose: the change is tried as v2 and compared on the test set (step 4), so that the prompt is not tuned on one example.

**Results (test set, 28 questions).** Scorers: 25/28 with the score guard (-2.0), 26/28 without it. Judge: correct 0.86, faithful 0.95. Failures: `t01` (the
2023 value before the current one, as predicted above), `t03` (hard paraphrase: retrieval misses, "I don't know"), `t12` (the guard cut an answerable question; best
chunk scored -2.41). `t16` is judged unfaithful: the model invented a deadline date. Two identical runs gave different text in 6 questions of 28 but the same verdicts.

## v2 (2026-11) - newest version first, named
**What changed.** Only rule 4. The version/date is said to be in each passage header; the value of the newest version goes first, in the first sentence, with the
version named; the older version only after it, with its value and date; "never start with the older version".
**Why.** Fix `t01` of v1 (older value first).
**Result: worse.** 23/28 with the guard, 24/28 without (v1: 25/26). Asking the model to name versions made it compare dates itself, and it did that wrongly: `t01` and
`t04` called the 2023 policy "latest/current" and gave its values (three days, 11:00-15:00) as the answer. `t10` lost its citations, `n03` stopped using the exact
"I don't know" sentence (hedged refusal; the scorer now accepts that). The judge was unchanged at 0.86 correct. Not used.
**Lesson.** A small model should not be asked to decide which version is newer.

## v3 (2026-11) - the code decides which version is newest
**What changed.** `version_marks` in `rag/answer/context.py` finds documents of the hits that share a title but have different dates (the year when there is no
date) and adds `NEWEST VERSION` / `OLDER VERSION` to the passage headers (only for prompts listed in `settings.VERSION_MARK_PROMPTS`, so v1 and v2 stay reproducible).
Rule 4 of the prompt uses the marks: answer from the NEWEST VERSION, then mention the OLDER VERSION in one sentence; "do not compare dates yourself".
**Result.** 26/28 with the guard, 27/28 without it (the best of the six runs); judge correct 0.86 / 0.89, faithful 0.95 / 1.00. `t01`, `t04`, `p01`, `p02` pass.
**Known side effect.** Two different documents with the same title and different dates are treated as versions: `t07` (`2009_library_pdf` and `2009_library_doc`) got
"... according to the OLDER VERSION ... However, the NEWEST VERSION ..." and mixed two systems. The scorers pass it (value and source are right); the judge does not.
A reliable version marker (a field in `corpus.yaml`) is the fix; not done.

## Judge prompts (`rag/prompts/judge_<version>.md`)
- **judge_v1** - two verdicts: `correct` (against the reference answer; for questions without an answer the answer must be a refusal; with no year in the
question the current value must be the answer) and `faithful` (every statement is in the cited passages). Agreement with 12 hand-rated answers: 11/12, kappa 0.82.
- **judge_v2** - adds: a reference that gives an answer, even a short "No, ...", is an answer, so "I don't know" is not correct (v1 confused "No, ..." with "no answer",
`c02`, three times out of three). 12/12, kappa 1.0 - measured on the same 12 answers where the error was seen, so optimistic.

