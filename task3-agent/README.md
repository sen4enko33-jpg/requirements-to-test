# Task 3: an agent over requirements documents

Part 3 of [`requirements-to-test`](../README.md). The RAG of [task 2](../task2-rag/) becomes an agent. The model itself
decides whether to search, which tool to call and when to answer. It answers questions about 42 documents (40 PURE
requirements specifications and the Remote Work Policy 2023 and 2026) with citations. It also creates test cases in
a TMS (test management system) through its own MCP server.

    question -> agent loop with limits -> tools (corpus search, TMS MCP server) -> answer with sources
                                       -> a person confirms every write first

## Run
Python 3.10+.

    cd task3-agent
    python3.11 -m venv .venv
    .venv/bin/pip install -r requirements.txt -r ../task2-rag/requirements.txt
    cp ../.env.example ../.env            # OPENROUTER_API_KEY=... (only in .env, never in git)
    cd ../task2-rag && ../task3-agent/.venv/bin/python -m rag.retrieval.build && cd -   # search index of task 2, once
    .venv/bin/python main.py "How many days a week can employees work remotely?"

`main.py` starts the MCP server, runs the agent and prints the answer, the stop reason, cost and the trace file.

    python main.py "Створи тест-кейс для вимоги про VPN у публічних Wi-Fi"   # asks y/N before writing (--answers y: in advance)
    python main.py "Які тест-кейси вже є в TMS?"
    python main.py "Покажи тест-кейс TC-0001"     # another team's: access denied (demo rows: python -m mcp_server.seed)
    FAULTS=search_corpus:503 python main.py "..." # fake failures: timeout, 429, 503, schema, lost
    python main.py "..." --max-steps 3 --max-cost 0.005

Tests without a model: `for t in tests/test_*.py; do .venv/bin/python $t | tail -1; done` (334 checks).
Evaluation on the model: `python -m evals.run --repeat 3` (about $0.07).

## Tools
Every tool does one thing. Descriptions are versioned files in [`prompts/tools/`](prompts/tools/); schemas are Pydantic
or the JSON Schema of the MCP server.

| tool | where | what it does | access |
|---|---|---|---|
| `search_corpus` | local (task 2 index) | hybrid search, passages with `ref`, marks the newest / older version | read only |
| `get_passage` | local | full text of one passage | read only |
| `list_documents` | local | documents and their metadata | read only |
| `list_test_cases` | MCP server | test cases of our team | read only |
| `get_test_case` | MCP server | one test case with steps | read only |
| `create_test_ticket` | local check, then MCP server | creates a test case for a requirement the agent has read | **writes to the TMS** (a person confirms first) |

Before writing, `create_test_ticket` checks that the requirement exists and was found in this conversation. Then the
code asks a person. The model never sees the server's `create_test_case`, so it cannot skip these steps.

## Limits and failures
- **Limits** per request: 8 model calls, 12 tool calls, 40k tokens, $0.02, 120 s; 20 s per tool call (`config.yaml`).
  On a limit the agent stops, returns what it has, and the reason goes to the trace.
- **Errors go back to the model as text** (`ERROR: invalid_args`, `unavailable`, `timeout`, `bad_output`, `forbidden`,
  ...), so a bad call is fixed and a broken service is reported honestly, without an invented answer.
- **Retries** with backoff only for read-only tools; a write runs once.
- **Answer schemas**: a renamed or missing field is an error in the trace, not a silent `None`.
- **Writes**: a person confirms each one (`y/N`, `--answers` in scripts, "no" without a terminal). An idempotency key
  (request + requirement) stops duplicates after a repeat or a lost answer.
- **Trace**: every model call, tool call, confirmation and stop is a JSON line in `traces/`
  (eval: `evals/runs/*/traces/`).

## The TMS MCP server
[`mcp_server/tms_server.py`](mcp_server/tms_server.py) serves the TMS (SQLite, `data/tms.db`):

| tool | who | what |
|---|---|---|
| `list_test_cases` | reader, writer | test cases of the caller's team |
| `get_test_case` | reader, writer | one test case; another team's -> `403`, unknown -> `404` |
| `create_test_case` | writer only | a new test case of the caller's team; the same idempotency key returns the existing one |

Restrictions on the server:
- fixed queries only: no SQL, shell or file path from the caller; every argument has a schema;
- reads are read-only at the database level; a reader does not even see `create_test_case`;
- a team sees and writes only its own rows; another team's data is `403`, a key used by another team is `409`;
- teams and roles are listed in [`access.yaml`](mcp_server/access.yaml); an unknown one stops the server at start;
- every decision (`ALLOW`, `DENY`, `CREATE`, `DUPLICATE`) is logged to `traces/mcp_tms.log`.

The team and role come from `TMS_TEAM` and `TMS_ROLE` (over HTTP they would come from a verified token). Run the server
alone or connect another client, for example Claude Code (Claude Desktop takes the same command in its config):

    TMS_TEAM=hr-policy-qa TMS_ROLE=reader .venv/bin/python -m mcp_server.tms_server
    claude mcp add tms -e TMS_TEAM=hr-policy-qa -e TMS_ROLE=reader -- /path/to/.venv/bin/python /path/to/mcp_server/tms_server.py

**How the agent uses it** ([`tools/mcp_tools.py`](tools/mcp_tools.py)): it starts the server for each request as team
`hr-policy-qa`, role writer. It takes the tools, their descriptions and schemas from the server, and limits, retries,
`FAULTS` and the trace work for them as for local tools. If the server does not start, the agent works without it and
creates no test cases.

### Why MCP and not plain function calling
- **Other users.** QA engineers open the same test cases from Claude Desktop or an IDE, and other teams' agents use the
  same TMS. One server serves everyone instead of a copy of the code in each client.
- **The rules live in one place.** Access, validation and duplicates are checked by the server for every client. The
  model cannot argue its way past a `403`.
- **Only the rights needed.** A reader gets no write tool, and each team sees only its rows. A function inside the agent
  would have full access to the database file.
- **Easy to replace.** The SQLite file can become a real TMS (TestRail, Jira) behind the same tools without changing the
  agent. The search stays local: only this agent uses it.

## Memory and feedback
Step 3 of the task (not yet): memory of the dialogue with a token limit, and feedback that changes the next answer.

## Prompts and evaluation
- [`prompts/system_v7.md`](prompts/system_v7.md) is the prompt in use; older versions are kept, and
  [`CHANGELOG.md`](prompts/CHANGELOG.md) says what changed in each version and which run showed the need.
- [`evals/`](evals/): 37 tasks in [`tasks.jsonl`](evals/tasks.jsonl) (written by `make_tasks.py`), deterministic
  checks in `checks.py`, the runner `run.py`, results and traces in `evals/runs/<date-time>/`.

| category | tasks | checks |
|---|---|---|
| answerable | a01-a10 | the answer and its citation, current vs old policy |
| no_tool | b01-b03 | greeting, the agent itself, arithmetic: no tool |
| unanswerable | c01-c03 | says the documents do not cover it, does not search forever |
| budget | d01 | "check every document": stops on the limit |
| fault | e01-e06, g06 | 503, timeout, 429, changed format, wrong argument, the MCP server down |
| side_effect | f01-f07 | confirmed, declined, unclear request, repeat, lost answer |
| access | g01-g02 | another team's data: 403, explains, no workaround |
| tms | g03-g05, g07 | own test cases through MCP, 404 |

Last full run (`evals/runs/20261128-152558`, 37 tasks x 3): 103/111 passed (93%), right tools 98%, 0 actions without
permission, $0.00064 per task. a03 and a10 fail every time; c02 and e06 failed once each (see the report).

## Layout
- `main.py`, `config.yaml` - the agent and its settings
- `agent/` - the loop, limits, model calls, trace, confirmation
- `tools/` - the tools, validation and retries (`registry.py`), MCP client (`mcp_tools.py`), TMS table (`tms.py`)
- `mcp_server/` - the server, `access.yaml`, demo data
- `prompts/`, `evals/`, `tests/`
- not in git: `.venv/`, `../.env`, the task 2 index, `data/tms.db`, `traces/`
