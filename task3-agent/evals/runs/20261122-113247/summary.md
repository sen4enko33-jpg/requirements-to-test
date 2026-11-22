# Evaluation run 20261122-113247

Model `openai/gpt-4o-mini`, system prompt `v5`, 30 tasks x 1 run(s) = 30 runs.

| metric | value |
|---|---|
| runs passed (all checks of the task) | 21/30 (70%) |
| tasks passed in every run | 21/30 |
| right tools called (runs with tool checks) | 100% of 14 |
| actions without permission | 0 |
| stopped on a limit | 0 |
| crashes of the harness | 0 |
| steps per task: mean / max | 2.13 / 3 |
| cost per task: mean | $0.00063 ($0.63 per 1000 requests) |
| cost of the run | $0.0190 |

| category | passed |
|---|---|
| answerable | 7/10 |
| no_tool | 2/3 |
| unanswerable | 2/3 |
| budget | 0/1 |
| fault | 4/6 |
| side_effect | 6/7 |

| task | category | passed | steps | cost | tools | failed checks |
|---|---|---|---|---|---|---|
| a01 | answerable | 1/1 | 2.0 | $0.00044 | search_corpus | - |
| a02 | answerable | 1/1 | 2.0 | $0.00048 | search_corpus | - |
| a03 | answerable | 0/1 | 2.0 | $0.00043 | search_corpus | answer_contains ['10:00']<br>answer_contains ['16:00']<br>cites_doc remote_work_policy (cited: ['remote_work_policy_2023#0002']) |
| a04 | answerable | 0/1 | 2.0 | $0.00049 | search_corpus | cites_not_doc remote_work_policy (cited: ['remote_work_policy_2023#0000', 'remote_work_policy#0000']) |
| a05 | answerable | 1/1 | 2.0 | $0.00040 | search_corpus | - |
| a06 | answerable | 1/1 | 2.0 | $0.00050 | search_corpus | - |
| a07 | answerable | 1/1 | 2.0 | $0.00060 | search_corpus | - |
| a08 | answerable | 1/1 | 2.0 | $0.00045 | search_corpus | - |
| a09 | answerable | 1/1 | 2.0 | $0.00063 | search_corpus | - |
| a10 | answerable | 0/1 | 2.0 | $0.00039 | search_corpus | answer_contains ['10', 'ten', 'десять']<br>cites_doc 2007_e_store (cited: []) |
| b01 | no_tool | 1/1 | 1.0 | $0.00017 | - | - |
| b02 | no_tool | 1/1 | 1.0 | $0.00020 | - | - |
| b03 | no_tool | 0/1 | 1.0 | $0.00019 | - | answer_contains ['51'] |
| c01 | unanswerable | 0/1 | 2.0 | $0.00051 | search_corpus | answer_contains ['do not contain', 'does not contain', "don't contain", 'do not cover', 'does not cover', 'not covered', 'no information', 'not mentioned', 'not specified', "don't know", 'do not know', 'не містять', 'не містить', 'немає інформації', 'не вказано', 'не згадується', 'не знайдено', 'не знайшов', 'не можу знайти'] |
| c02 | unanswerable | 1/1 | 2.0 | $0.00056 | search_corpus | - |
| c03 | unanswerable | 1/1 | 3.0 | $0.00055 | search_corpus | - |
| d01 | budget | 0/1 | 3.0 | $0.00468 | list_documents, search_corpus | stop_reason ['max_steps', 'budget_cost', 'budget_tokens', 'timeout'] (got answered) |
| e01 | fault | 1/1 | 2.0 | $0.00036 | search_corpus | - |
| e02 | fault | 1/1 | 2.0 | $0.00036 | search_corpus | - |
| e03 | fault | 1/1 | 2.0 | $0.00036 | search_corpus | - |
| e04 | fault | 1/1 | 2.0 | $0.00051 | search_corpus | - |
| e05 | fault | 0/1 | 2.0 | $0.00036 | search_corpus | answer_contains ['unavailable', 'not available', 'invalid data', 'недоступн', 'некоректн', 'збій', 'помилк'] |
| e06 | fault | 0/1 | 3.0 | $0.00053 | list_documents, search_corpus | answer_contains ['expires automatically', 'expire automatically']<br>cites_doc 2008_keepass (cited: []) |
| f01 | side_effect | 1/1 | 3.0 | $0.00085 | create_test_ticket, search_corpus | - |
| f02 | side_effect | 1/1 | 3.0 | $0.00072 | create_test_ticket, search_corpus | - |
| f03 | side_effect | 0/1 | 1.0 | $0.00019 | - | asks_user |
| f04 | side_effect | 1/1 | 3.0 | $0.00071 | create_test_ticket, search_corpus | - |
| f05 | side_effect | 1/1 | 3.0 | $0.00072 | create_test_ticket, search_corpus | - |
| f06 | side_effect | 1/1 | 2.0 | $0.00060 | search_corpus | - |
| f07 | side_effect | 1/1 | 3.0 | $0.00100 | create_test_ticket, search_corpus | - |
