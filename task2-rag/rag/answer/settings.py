"""Settings of the answering step. MIN_SCORE is the lowest reranker score of the best chunk for which the model is still
asked (below it the answer is "I don't know" without a model call). None = the guard is off; it is set from the dev
questions (rag/eval/dev_questions.jsonl), never from the test set."""
PROMPT_VERSION = "v1"
CONTEXT_BUDGET_TOKENS = 3000
TOP_K = 10
# Prompt versions whose context marks NEWEST VERSION / OLDER VERSION in the passage headers (v1 and v2 are measured without it).
VERSION_MARK_PROMPTS = {"v3"}
SAMPLING = {"temperature": 0.0, "top_p": 1.0}
# Chosen on rag/eval/dev_questions.jsonl (5 answerable, 6 unanswerable questions): the best chunk of an answerable question
# scored from -1.47 to 9.01, of an unanswerable one from -11.05 to 3.19. The ranges overlap, so one threshold cannot separate
# them: -2.0 (a margin of 0.5 below the lowest answerable score) removes only the clearly unrelated questions (3 of 6 here);
# "on topic but not in the documents" is left to rule 2 of the prompt. Eleven questions are a small sample.
MIN_SCORE: float | None = -2.0
