# Changelog of the prompts

Versions of the system prompt are `prompts/system_<version>.md` (the one in use is `system_prompt` of `config.yaml`).
Tool descriptions are `prompts/tools/<name>.yaml` with a `version` field; their changes are listed here too.

## create_test_ticket v2 (step 2.4)
- "test-case tracker" -> "TMS (test management system)": the store of the test cases was renamed everywhere (database
  data/tms.db, server mcp_server/tms_server.py, MCP server name tms), the description uses the same word. No change in
  what the tool does.

## system_v7 (step 2.4, the TMS MCP server)
- The intro names the TMS (test management system) and its tools (list_test_cases, get_test_case of the MCP server), and
  new rule 9 says when to use them. With v6, "Які тест-кейси вже є в трекері?" (task g07; reworded "... в TMS?" when the
  tracker was renamed TMS) failed 3 of 3 runs: the agent called no tool and asked back
  "which test cases are you interested in? name a document or a requirement", because v6 knew only the corpus tools and
  rule 8 (ask when the requirement is unclear) was the closest rule. With a document named (g04) v6 already listed them.
- Rule 6 gets forbidden (a decision of the server: no workaround, explain) and not_found (say so, invent nothing). v6
  already behaved so in g01, g02, g05 (18 of 18 runs) thanks to the text of the server's error; the rule makes it not
  depend on that text.

## system_v6 (step 1.5, after the first evaluation run)
- Rule 1: general questions (arithmetic and the like) are answered without tools. In the first run (task b03) v5 refused
  "17 x 3" ("this is an arithmetic question, I cannot answer it"), reading rule 2 (facts only from tools) as a ban on
  everything that is not in the documents.

## list_documents v2 (step 1.5)
- `title_contains` also matches the doc_id. In task e06 the agent looked for "keepass", got 0 documents (the title is the
  generic "Software Requirements Specification", the name is only in the doc_id 2008_keepass) and gave up.

## system_v5 (step 1.4)
- Rule 8 rewritten. With v4 the agent never created a test case: in 5 of 5 real runs with a clear requirement it asked the
  user for "a title and steps" instead, because "never guess" was read as "ask for everything". The confirmation is now
  done by code, so v5 tells the model to write title, steps and expected result itself, call the tool, and ask only when
  the requirement itself is unclear. Two versions of a requirement: the newest one.
- Rule 0: answer in the language of the user's message. v2-v4 answered "Привіт!" in English.

## system_v4 (step 1.4)
- Rule 8 for create_test_ticket: find the requirement first, ask the user when the requirement is unclear (several or no
  candidates) instead of picking one, take the expected result from the requirement, one test case per request, do not
  retry after the user declined, report the ticket number or that it already existed.

## create_test_ticket v1 (step 1.4)
- The first tool with a side effect: when to call it (the user asked AND the requirement ref came from a search), when
  not (questions, guessed requirements), arguments, idempotent repeat (`duplicate`: true).

## system_v3 (step 1.3)
- Rule 6 splits the tool errors: wrong calls (fix and retry) and service failures (unavailable, rate_limited, timeout,
  bad_output: say the service failed). With `FAULTS=search_corpus:schema` v2 answered "the documents do not contain this
  information" although they do: a broken service was reported as a missing answer.
- Rule 4: the search query is always English. With v2 the model still sent a Cyrillic query first in most runs and lost a
  step on the rejection.

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
