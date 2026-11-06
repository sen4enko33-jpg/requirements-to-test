# Retrieval results

15 hand-checked questions (`rag/eval/retrieval_questions.jsonl`). A chunk is relevant when it comes from the question's document and contains the evidence quote. Configuration (fixed before the run): top 10, 50 candidates from each of vector and BM25, RRF k=60, the reranker re-orders the top 20.

| chunking | search | recall@1 | recall@3 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|---|---|
| structural-v1 | vector | 0.47 | 0.67 | 0.73 | 0.87 | 0.60 |
| structural-v1 | hybrid | 0.53 | 0.87 | 0.87 | 0.87 | 0.68 |
| structural-v1 | hybrid_rerank | 0.67 | 0.80 | 0.93 | 0.93 | 0.76 |
| fixed-300 | vector | 0.33 | 0.53 | 0.67 | 0.93 | 0.49 |
| fixed-300 | hybrid | 0.53 | 0.80 | 0.93 | 1.00 | 0.69 |
| fixed-300 | hybrid_rerank | 0.60 | 0.93 | 1.00 | 1.00 | 0.78 |

Rank of the first relevant chunk per question (`-` = not in the top 10):

| id | type | document | struc vector | struc hybrid | struc hybrid_rerank | fixed vector | fixed hybrid | fixed hybrid_rerank |
|---|---|---|---|---|---|---|---|---|
| q01 | paraphrase | remote_work_policy | 2 | 1 | 2 | 1 | 1 | 2 |
| q02 | plain | remote_work_policy | 2 | 1 | 1 | 1 | 1 | 1 |
| q04 | paraphrase | remote_work_policy | 2 | 2 | 1 | 10 | 3 | 1 |
| q05 | hard_paraphrase | remote_work_policy | 9 | - | - | 1 | 8 | 4 |
| q06 | twin_pair | 2009_library_doc | 1 | 1 | 1 | 4 | 1 | 1 |
| q07 | twin_pair | 2009_library_pdf | 1 | 1 | 1 | 1 | 1 | 1 |
| q08 | twin_pair | 2007_eirene_fun_7 | 1 | 1 | 1 | 3 | 1 | 1 |
| q10 | twin_pair | 2005_clarus_low | 5 | 3 | 2 | 6 | 3 | 2 |
| q12 | identifier | 2008_keepass | - | - | 1 | 7 | 4 | 1 |
| q13 | identifier | 2000_nasa_x38 | - | 2 | 5 | 6 | 1 | 2 |
| q15 | number | 2007_e_store | 1 | 1 | 1 | 2 | 2 | 1 |
| q19 | table | 2004_jse | 7 | 3 | 1 | 5 | 1 | 1 |
| q22 | version_old | remote_work_policy_2023 | 1 | 2 | 1 | 1 | 1 | 2 |
| q25 | version_old | remote_work_policy_2023 | 1 | 1 | 1 | - | 4 | 1 |
| q26 | version_current | remote_work_policy | 1 | 1 | 4 | 2 | 2 | 2 |
