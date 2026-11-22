# Changelog of the prompts

Versions of the system prompt are `prompts/system_<version>.md` (the one in use is `system_prompt` of `config.yaml`).
Tool descriptions are `prompts/tools/<name>.yaml` with a `version` field; their changes are listed here too.

## search_corpus v2 (step 1.2)
- The query must be in English. In the first real run the model searched in Ukrainian ("дні на тиждень віддалена робота"),
  found nothing twice and answered that the documents do not cover a question they answer. The description says so more
  strongly and the code now rejects a query in Cyrillic with `ERROR: invalid_args`, so the model translates and retries.

## system_v2 (step 1.2)
- Describes the corpus and the three corpus tools.
- Facts only from tool results, citations by `ref` in square brackets.
- At most one extra search after a miss, then "the documents do not cover it" (against endless searching).
- Version rule (newest first) for the passages marked NEWEST VERSION / OLDER VERSION, as `answer_v3` of task 2.

## tools v1 (step 1.2)
- `search_corpus` v1, `get_passage` v1, `list_documents` v1: when to call, when not, arguments, what comes back.

## system_v1 (step 1.1)
- First version: when to call a tool, no invented results, how to read `ERROR:` results of tools, short answers.
