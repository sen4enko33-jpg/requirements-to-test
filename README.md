# requirements-to-test

Capstone project of an AI-engineering course, built around software requirements documents. The repository has two
independent parts; each one has its own README, report, requirements and tests.

| part | what it does | README | report |
|---|---|---|---|
| [`task1-extraction/`](task1-extraction/) | Homework 1: a language model extracts structured requirements from the text of a requirements document; comparison of models and prompts on a labelled set | [README](task1-extraction/README.md) | [REPORT](task1-extraction/REPORT.md) |
| [`task2-rag/`](task2-rag/) | Homework 2: RAG over 42 requirements documents - ingestion, chunking, Chroma + BM25 + reranking, answers with citations, evaluation | [README](task2-rag/README.md) | [REPORT](task2-rag/REPORT.md) |

## What lies where
- `task1-extraction/` - the extraction pipeline (`main.py`, `src/`), prompts, data splits, results of all experiments, `tests/`, `config.yaml`
- `task2-rag/` - the `rag/` package (ingest, chunking, retrieval, answer, eval, prompts, llm), its data and labelled questions, `tests/`, `config.yaml`
- `requirements.txt` - both parts together (`pip install -r requirements.txt`); each part also has its own file
- `.env` / `.env.example` - `OPENROUTER_API_KEY`; one file in the repository root is read by both parts (a `.env` inside a part wins)
- `.github/workflows/eval.yml` - CI: tests of both parts and the evaluation of task 2 with failing thresholds (push, pull request; manual run adds the model answers and the judge, needs the secret `OPENROUTER_API_KEY`)
- `.gitignore` - generic patterns; each part has its own `.gitignore` for its generated files

## How to run
Always change into the folder of the part first; commands and paths in the READMEs are relative to it.

    cp .env.example .env                        # put OPENROUTER_API_KEY into .env
    # part 1
    cd task1-extraction && pip install -r requirements.txt && python main.py
    # part 2
    cd task2-rag && pip install -r requirements.txt && python -m rag.answer.cli "your question"

Tests (no network, no API key): in `task1-extraction/` run `python tests/test_repair.py`, `python tests/test_limits.py`,
`python tests/test_prompt_defs.py`; in `task2-rag/` run every `tests/test_*.py`.

Data: the requirements documents come from the PURE dataset (public requirements documents), see the README of each part.
