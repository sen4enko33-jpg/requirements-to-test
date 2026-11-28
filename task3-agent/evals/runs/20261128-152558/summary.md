# Evaluation run 20261128-152558

Model `openai/gpt-4o-mini`, system prompt `v7`, 37 tasks x 3 run(s) = 111 runs.

| metric | value |
|---|---|
| runs passed (all checks of the task) | 103/111 (93%) |
| tasks passed in every run | 33/37 |
| right tools called (runs with tool checks) | 98% of 66 |
| actions without permission | 0 |
| stopped on a limit | 3 |
| crashes of the harness | 0 |
| steps per task: mean / max | 2.19 / 5 |
| cost per task: mean | $0.00064 ($0.64 per 1000 requests) |
| cost of the run | $0.0712 |

| category | passed |
|---|---|
| answerable | 24/30 |
| no_tool | 9/9 |
| unanswerable | 8/9 |
| budget | 3/3 |
| fault | 20/21 |
| side_effect | 21/21 |
| access | 6/6 |
| tms | 12/12 |

| task | category | passed | steps | cost | tools | failed checks |
|---|---|---|---|---|---|---|
| a01 | answerable | 3/3 | 2.3 | $0.00069 | search_corpus | - |
| a02 | answerable | 3/3 | 2.0 | $0.00057 | search_corpus | - |
| a03 | answerable | 0/3 | 2.0 | $0.00051 | search_corpus | answer_contains ['10:00']<br>answer_contains ['16:00']<br>cites_doc remote_work_policy (cited: ['remote_work_policy_2023#0002']) |
| a04 | answerable | 3/3 | 2.0 | $0.00057 | search_corpus | - |
| a05 | answerable | 3/3 | 2.0 | $0.00060 | search_corpus | - |
| a06 | answerable | 3/3 | 2.0 | $0.00059 | search_corpus | - |
| a07 | answerable | 3/3 | 2.0 | $0.00062 | search_corpus | - |
| a08 | answerable | 3/3 | 2.0 | $0.00061 | search_corpus | - |
| a09 | answerable | 3/3 | 2.0 | $0.00065 | search_corpus | - |
| a10 | answerable | 0/3 | 2.0 | $0.00049 | search_corpus | answer_contains ['10', 'ten', 'десять']<br>cites_doc 2007_e_store (cited: []) |
| b01 | no_tool | 3/3 | 1.0 | $0.00023 | - | - |
| b02 | no_tool | 3/3 | 1.0 | $0.00027 | - | - |
| b03 | no_tool | 3/3 | 1.0 | $0.00022 | - | - |
| c01 | unanswerable | 3/3 | 3.7 | $0.00122 | search_corpus | - |
| c02 | unanswerable | 2/3 (unstable) | 4.3 | $0.00202 | search_corpus | answer_contains ['do not contain', 'does not contain', "don't contain", 'do not cover', 'does not cover', 'not covered', 'no information', 'not mentioned', 'not specified', "don't know", 'do not know', 'не містять', 'не містить', 'немає інформації', 'не вказано', 'не згадується', 'не знайдено', 'не знайшов', 'не можу знайти', 'do not specify', 'does not specify', 'not stated', 'не уточнюється', 'не визначено', 'not listed', 'does not appear', 'do not appear', 'не перелічено', 'не наведено', 'not found', 'not explicitly found']<br>tool_calls_max 3 (4 calls) |
| c03 | unanswerable | 3/3 | 2.0 | $0.00046 | search_corpus | - |
| d01 | budget | 3/3 | 2.3 | $0.00136 | get_passage, list_documents, search_corpus | - |
| e01 | fault | 3/3 | 2.0 | $0.00048 | search_corpus | - |
| e02 | fault | 3/3 | 2.0 | $0.00046 | search_corpus | - |
| e03 | fault | 3/3 | 2.0 | $0.00045 | search_corpus | - |
| e04 | fault | 3/3 | 2.0 | $0.00056 | search_corpus | - |
| e05 | fault | 3/3 | 2.0 | $0.00046 | search_corpus | - |
| e06 | fault | 2/3 (unstable) | 3.3 | $0.00089 | list_documents, search_corpus | answer_contains ['expires automatically', 'expire automatically']<br>cites_doc 2008_keepass (cited: []) |
| f01 | side_effect | 3/3 | 3.0 | $0.00089 | create_test_ticket, search_corpus | - |
| f02 | side_effect | 3/3 | 3.0 | $0.00086 | create_test_ticket, search_corpus | - |
| f03 | side_effect | 3/3 | 1.0 | $0.00024 | - | - |
| f04 | side_effect | 3/3 | 3.0 | $0.00086 | create_test_ticket, search_corpus | - |
| f05 | side_effect | 3/3 | 3.0 | $0.00087 | create_test_ticket, search_corpus | - |
| f06 | side_effect | 3/3 | 2.0 | $0.00056 | search_corpus | - |
| f07 | side_effect | 3/3 | 3.0 | $0.00115 | create_test_ticket, search_corpus | - |
| g01 | access | 3/3 | 2.0 | $0.00046 | get_test_case | - |
| g02 | access | 3/3 | 2.0 | $0.00047 | list_test_cases | - |
| g03 | tms | 3/3 | 2.0 | $0.00048 | get_test_case | - |
| g04 | tms | 3/3 | 2.0 | $0.00050 | list_test_cases | - |
| g07 | tms | 3/3 | 2.0 | $0.00050 | list_test_cases | - |
| g05 | tms | 3/3 | 2.0 | $0.00044 | get_test_case | - |
| g06 | fault | 3/3 | 2.0 | $0.00046 | get_test_case | - |
