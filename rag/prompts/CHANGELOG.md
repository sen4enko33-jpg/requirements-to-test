# RAG prompt changelog

Prompts live in `rag/prompts/answer_<version>.md` and are loaded by `rag/answer/prompts.py` (`build_prompt("v1", context, question)`).
Each entry records what changed and why; results are added after the evaluation run (step 4).

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

**Results.** To be added after the evaluation run.
