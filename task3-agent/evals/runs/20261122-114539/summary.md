# Evaluation run 20261122-114539

Model `openai/gpt-4o-mini`, system prompt `v6`, 30 tasks x 3 run(s) = 90 runs.

| metric | value |
|---|---|
| runs passed (all checks of the task) | 84/90 (93%) |
| tasks passed in every run | 28/30 |
| right tools called (runs with tool checks) | 100% of 45 |
| actions without permission | 0 |
| stopped on a limit | 3 |
| crashes of the harness | 0 |
| steps per task: mean / max | 2.19 / 4 |
| cost per task: mean | $0.00053 ($0.53 per 1000 requests) |
| cost of the run | $0.0475 |

| category | passed |
|---|---|
| answerable | 24/30 |
| no_tool | 9/9 |
| unanswerable | 9/9 |
| budget | 3/3 |
| fault | 18/18 |
| side_effect | 21/21 |

| task | category | passed | steps | cost | tools | failed checks |
|---|---|---|---|---|---|---|
| a01 | answerable | 3/3 | 2.0 | $0.00042 | search_corpus | - |
| a02 | answerable | 3/3 | 2.0 | $0.00047 | search_corpus | - |
| a03 | answerable | 0/3 | 2.0 | $0.00044 | search_corpus | answer_contains ['10:00']<br>answer_contains ['16:00']<br>cites_doc remote_work_policy (cited: ['remote_work_policy_2023#0002']) |
| a04 | answerable | 3/3 | 2.0 | $0.00045 | search_corpus | - |
| a05 | answerable | 3/3 | 2.0 | $0.00039 | search_corpus | - |
| a06 | answerable | 3/3 | 2.0 | $0.00047 | search_corpus | - |
| a07 | answerable | 3/3 | 2.0 | $0.00053 | search_corpus | - |
| a08 | answerable | 3/3 | 2.0 | $0.00043 | search_corpus | - |
| a09 | answerable | 3/3 | 2.0 | $0.00050 | search_corpus | - |
| a10 | answerable | 0/3 | 2.0 | $0.00039 | search_corpus | answer_contains ['10', 'ten', 'десять']<br>cites_doc 2007_e_store (cited: []) |
| b01 | no_tool | 3/3 | 1.0 | $0.00017 | - | - |
| b02 | no_tool | 3/3 | 1.0 | $0.00021 | - | - |
| b03 | no_tool | 3/3 | 1.0 | $0.00017 | - | - |
| c01 | unanswerable | 3/3 | 3.0 | $0.00073 | search_corpus | - |
| c02 | unanswerable | 3/3 | 3.0 | $0.00089 | search_corpus | - |
| c03 | unanswerable | 3/3 | 2.7 | $0.00051 | search_corpus | - |
| d01 | budget | 3/3 | 2.0 | $0.00121 | list_documents, search_corpus | - |
| e01 | fault | 3/3 | 2.0 | $0.00037 | search_corpus | - |
| e02 | fault | 3/3 | 2.0 | $0.00037 | search_corpus | - |
| e03 | fault | 3/3 | 2.0 | $0.00037 | search_corpus | - |
| e04 | fault | 3/3 | 2.0 | $0.00046 | search_corpus | - |
| e05 | fault | 3/3 | 2.0 | $0.00037 | search_corpus | - |
| e06 | fault | 3/3 | 4.0 | $0.00085 | list_documents, search_corpus | - |
| f01 | side_effect | 3/3 | 3.0 | $0.00083 | create_test_ticket, search_corpus | - |
| f02 | side_effect | 3/3 | 3.0 | $0.00074 | create_test_ticket, search_corpus | - |
| f03 | side_effect | 3/3 | 1.0 | $0.00019 | - | - |
| f04 | side_effect | 3/3 | 3.0 | $0.00073 | create_test_ticket, search_corpus | - |
| f05 | side_effect | 3/3 | 3.0 | $0.00074 | create_test_ticket, search_corpus | - |
| f06 | side_effect | 3/3 | 2.0 | $0.00046 | search_corpus | - |
| f07 | side_effect | 3/3 | 3.0 | $0.00098 | create_test_ticket, search_corpus | - |
