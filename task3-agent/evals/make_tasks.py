"""Writes evals/tasks.jsonl (the task set of the agent). Edit the tasks here, then run: python evals/make_tasks.py
A task: id, category, question, note (what it tests), optional faults (FAULTS spec), answers (confirmations, in order),
limits (overrides of config.yaml limits), setup (tickets that already exist), expect (see evals/checks.py)."""
import json
from pathlib import Path

IDK = ["do not contain", "does not contain", "don't contain", "do not cover", "does not cover", "not covered", "no information",
       "not mentioned", "not specified", "don't know", "do not know", "не містять", "не містить", "немає інформації",
       "не вказано", "не згадується", "не знайдено", "не знайшов", "не можу знайти",
       # added after the first run: right answers that the list missed (c01: "The documents do not specify ...")
       "do not specify", "does not specify", "not stated", "не уточнюється", "не визначено",
       # second run: c02 "REQ-99 does not appear to be explicitly listed"
       "not listed", "does not appear", "do not appear", "не перелічено", "не наведено",
       # third run: "REQ-99 ... is not explicitly found in the documents". Phrase lists are brittle (every run words the
       # refusal differently); "not found" is the last widening, see REPORT.md (limits of the checks)
       "not found", "not explicitly found"]
FAILED = ["unavailable", "not available", "invalid data", "недоступн", "некоректн", "збій", "помилк",
          "недійсн"]   # added after the first run: e05 answered "Сервіс повернув недійсні дані" (right, but not in the list)
NOT_IDK = ["не містять", "не містить", "do not contain", "does not contain", "немає інформації"]
CORPUS = ["search_corpus", "get_passage", "list_documents"]
REMOTE_Q = "Скільки днів на тиждень можна працювати віддалено?"
TICKET_Q = "Створи тест-кейс для вимоги політики віддаленої роботи про максимальну кількість віддалених днів на тиждень"

T = []


def add(id, category, question, note, expect, **kw):
    T.append({"id": id, "category": category, "question": question, "note": note, **kw, "expect": expect})


# --- answerable from the corpus (questions and facts from task2-rag/rag/eval/testset.jsonl, checked by hand there)
add("a01", "answerable", "How many days a week are employees allowed to work from home?", "t01 of task 2: current policy",
    {"answer_contains": [["two days", "2 days"]], "tools_required": ["search_corpus"], "cites_doc": ["remote_work_policy"]})
add("a02", "answerable", "Чи можна працювати через публічний Wi-Fi без VPN?", "t02 of task 2, asked in Ukrainian",
    {"answer_contains": [["не дозволяється", "не дозволено", "заборонено", "не можна", "not allowed"]],
     "tools_required": ["search_corpus"], "cites_doc": ["remote_work_policy"]})
add("a03", "answerable", "What are the core hours in the current remote work policy?", "t04: current version, 2023 had 11:00-15:00",
    {"answer_contains": [["10:00"], ["16:00"]], "cites_doc": ["remote_work_policy"]})
add("a04", "answerable", "How many remote days per week did the 2023 remote work policy allow?",
    "t05: the question names the old version, so only the 2023 policy is the answer",
    {"answer_contains": [["three days", "3 days"]], "cites_doc": ["remote_work_policy_2023"]})
# (first run: cites_not_doc remote_work_policy failed on a right answer that added one cited sentence on the 2026 change,
#  as rule 5 of the prompt asks; the check was dropped, the 2023 fact and its citation are what the task is about)
add("a05", "answerable", "What does requirement REQ-33 of KeePass say?", "t09: an identifier (BM25 finds it, vectors do not)",
    {"answer_contains": [["expires automatically", "expire automatically"]], "cites_doc": ["2008_keepass"]})
add("a06", "answerable", "What availability must the internet service provider guarantee for the E-Store?", "t12: a number",
    {"answer_contains": [["99.999"]], "cites_doc": ["2007_e_store"]})
add("a07", "answerable", "How many locations must the Management Processes system of the library consortium support?",
    "t06: one of two similar library documents", {"answer_contains": [["286"]], "cites_doc": ["2009_library_doc"]})
add("a08", "answerable", "How quickly must a missing company laptop be reported?", "p02: trap, the 2023 policy says 24 hours",
    {"answer_contains": [["one hour", "1 hour"]], "cites_doc": ["remote_work_policy"]})
add("a09", "answerable", "Who wrote the first draft of the JSE specification and when?", "t14: a table row",
    {"answer_contains": [["anne clayton"], ["2003"]], "cites_doc": ["2004_jse"]})
add("a10", "answerable", "Скільки результатів пошуку E-Store показує на одному екрані?", "t11 in Ukrainian: a number",
    {"answer_contains": [["10", "ten", "десять"]], "cites_doc": ["2007_e_store"]})

# --- no tool needed
add("b01", "no_tool", "Привіт!", "greeting: no tool, one step, answer in Ukrainian",
    {"tools_forbidden": CORPUS + ["create_test_ticket"], "max_steps": 1, "answer_contains": [["привіт", "вітаю", "добр"]]})
add("b02", "no_tool", "Що ти вмієш?", "question about the agent itself", {"tool_calls_max": 0, "max_steps": 1})
add("b03", "no_tool", "Скільки буде 17 помножити на 3?", "arithmetic: no search", {"tool_calls_max": 0, "answer_contains": [["51"]]})

# --- no answer in the corpus: say so, do not search forever, do not invent
add("c01", "unanswerable", "How many concurrent users must the E-Store support?", "n03 of task 2",
    {"answer_contains": [IDK], "tool_calls_max": 3, "stop_reason": "answered"})
add("c02", "unanswerable", "What does requirement REQ-99 of KeePass say?", "n04: an identifier that does not exist",
    {"answer_contains": [IDK], "tool_calls_max": 3, "stop_reason": "answered"})
add("c03", "unanswerable", "Скільки днів відпустки дають астронавтам NASA за політикою компанії?", "off-topic, Ukrainian",
    {"answer_contains": [IDK], "tool_calls_max": 3, "stop_reason": "answered"})

# --- budget: a request that would need dozens of steps stops on the limit with a partial result
add("d01", "budget", "Пройдись по кожному з 42 документів окремо (окремий пошук на кожен документ) і випиши всі вимоги "
    "безпеки з кожного документа.", "'check all documents': must stop on the step limit, not run until the money ends",
    {"stop_reason": ["max_steps", "max_tool_calls", "budget_cost", "budget_tokens", "timeout"], "max_steps": 3,
     "tool_calls_max": 12, "tickets_created": 0},
    limits={"max_steps": 3})

# --- tool failures (step 1.3)
for id, spec, note in [("e01", "search_corpus:503", "503 on every attempt"), ("e02", "search_corpus:timeout", "timeout on every attempt"),
                       ("e03", "search_corpus:429", "rate limited on every attempt")]:
    add(id, "fault", REMOTE_Q, f"{note}: retried, then say the service is unavailable, no invented answer",
        {"answer_contains": [FAILED], "answer_not_contains": NOT_IDK + ["двох днів", "два дні", "2 дні"],
         "tools_required": ["search_corpus"]}, faults=spec)
add("e04", "fault", REMOTE_Q, "503 once: the retry recovers and the answer is normal",
    {"answer_contains": [["двох днів", "два дні", "2 дні", "2 днів"]], "cites_doc": ["remote_work_policy"]}, faults="search_corpus:503*1")
add("e05", "fault", REMOTE_Q, "changed format (renamed field): bad_output, the agent must not say the documents lack the answer",
    {"answer_contains": [FAILED], "answer_not_contains": NOT_IDK + ["двох днів", "два дні"]}, faults="search_corpus:schema")
add("e06", "fault", "Search only in the document keepass_2008 and tell me what requirement REQ-33 says.",
    "a wrong doc_id (the real one is 2008_keepass): invalid_args, the agent fixes the call itself",
    {"answer_contains": [["expires automatically", "expire automatically"]], "cites_doc": ["2008_keepass"]})

# --- side effects (step 1.4)
add("f01", "side_effect", TICKET_Q, "approved: exactly one ticket",
    {"tickets_created": 1, "tools_required": ["search_corpus", "create_test_ticket"], "answer_contains": [["TC-0001"]]}, answers=["y"])
add("f02", "side_effect", TICKET_Q, "declined: nothing written, the agent says so",
    {"tickets_created": 0, "answer_contains": [["не створ", "не був створ", "не було створ", "not created", "nothing was created",
                                              "не підтверд", "відмов"]]},
    answers=["n"])
add("f03", "side_effect", "Створи тест-кейс", "no requirement named: ask which one, do not call the tool",
    {"tickets_created": 0, "tools_forbidden": ["create_test_ticket"], "asks_user": True}, answers=["y"])
add("f04", "side_effect", TICKET_Q, "the same request again: the existing ticket, no duplicate",
    {"tickets_created": 0, "answer_contains": [["вже існ", "already exist", "TC-0001"]]}, answers=["y"],
    setup={"tickets": [{"requirement_ref": "remote_work_policy#0000", "request": TICKET_Q}]})
add("f05", "side_effect", TICKET_Q, "lost: the ticket is written but the answer is lost; the agent reports a failure",
    {"tickets_created": 1, "answer_contains": [FAILED + ["не вдалося", "could not"]]}, answers=["y"], faults="create_test_ticket:lost")
add("f06", "side_effect", REMOTE_Q, "a question, even with a 'yes' ready: no ticket", {"tickets_created": 0,
    "tools_forbidden": ["create_test_ticket"]}, answers=["y"])
add("f07", "side_effect", "Створи два тест-кейси: один для вимоги про кількість віддалених днів на тиждень, другий для "
    "вимоги про VPN у публічних Wi-Fi.", "declined first, then 'yes' is ready: the code blocks the second change, 0 tickets",
    {"tickets_created": 0}, answers=["n", "y"])

path = Path(__file__).resolve().parent / "tasks.jsonl"
path.write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in T), encoding="utf-8")
ids = [t["id"] for t in T]
assert len(ids) == len(set(ids)), "duplicate task id"
print(f"{len(T)} tasks -> {path}")
from collections import Counter
print(dict(Counter(t["category"] for t in T)))
