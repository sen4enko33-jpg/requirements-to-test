# Evaluation run 20261128-145738

Model `openai/gpt-4o-mini`, system prompt `v7`, 37 tasks x 3 run(s) = 111 runs.

| metric | value |
|---|---|
| runs passed (all checks of the task) | 105/111 (95%) |
| tasks passed in every run | 35/37 |
| right tools called (runs with tool checks) | 100% of 66 |
| actions without permission | 0 |
| stopped on a limit | 3 |
| crashes of the harness | 0 |
| steps per task: mean / max | 2.15 / 4 |
| cost per task: mean | $0.00062 ($0.62 per 1000 requests) |
| cost of the run | $0.0686 |

| category | passed |
|---|---|
| answerable | 24/30 |
| no_tool | 9/9 |
| unanswerable | 9/9 |
| budget | 3/3 |
| fault | 21/21 |
| side_effect | 21/21 |
| access | 6/6 |
| tracker | 12/12 |

| task | category | passed | steps | cost | tools | failed checks |
|---|---|---|---|---|---|---|
| a01 | answerable | 3/3 | 2.0 | $0.00058 | search_corpus | - |
| a02 | answerable | 3/3 | 2.0 | $0.00059 | search_corpus | - |
| a03 | answerable | 0/3 | 2.0 | $0.00053 | search_corpus | answer_contains ['10:00']<br>answer_contains ['16:00']<br>cites_doc remote_work_policy (cited: ['remote_work_policy_2023#0002']) |
| a04 | answerable | 3/3 | 2.0 | $0.00058 | search_corpus | - |
| a05 | answerable | 3/3 | 2.0 | $0.00057 | search_corpus | - |
| a06 | answerable | 3/3 | 2.0 | $0.00058 | search_corpus | - |
| a07 | answerable | 3/3 | 2.0 | $0.00066 | search_corpus | - |
| a08 | answerable | 3/3 | 2.0 | $0.00054 | search_corpus | - |
| a09 | answerable | 3/3 | 2.0 | $0.00065 | search_corpus | - |
| a10 | answerable | 0/3 | 2.7 | $0.00072 | search_corpus | answer_contains ['10', 'ten', 'десять']<br>cites_doc 2007_e_store (cited: []) |
| b01 | no_tool | 3/3 | 1.0 | $0.00023 | - | - |
| b02 | no_tool | 3/3 | 1.0 | $0.00026 | - | - |
| b03 | no_tool | 3/3 | 1.0 | $0.00022 | - | - |
| c01 | unanswerable | 3/3 | 3.0 | $0.00093 | search_corpus | - |
| c02 | unanswerable | 3/3 | 3.0 | $0.00123 | search_corpus | - |
| c03 | unanswerable | 3/3 | 2.0 | $0.00046 | search_corpus | - |
| d01 | budget | 3/3 | 2.0 | $0.00129 | list_documents, search_corpus | - |
| e01 | fault | 3/3 | 2.0 | $0.00052 | search_corpus | - |
| e02 | fault | 3/3 | 2.0 | $0.00046 | search_corpus | - |
| e03 | fault | 3/3 | 2.0 | $0.00046 | search_corpus | - |
| e04 | fault | 3/3 | 2.0 | $0.00056 | search_corpus | - |
| e05 | fault | 3/3 | 2.0 | $0.00047 | search_corpus | - |
| e06 | fault | 3/3 | 4.0 | $0.00105 | list_documents, search_corpus | - |
| f01 | side_effect | 3/3 | 3.0 | $0.00089 | create_test_ticket, search_corpus | - |
| f02 | side_effect | 3/3 | 3.0 | $0.00086 | create_test_ticket, search_corpus | - |
| f03 | side_effect | 3/3 | 1.0 | $0.00024 | - | - |
| f04 | side_effect | 3/3 | 3.0 | $0.00085 | create_test_ticket, search_corpus | - |
| f05 | side_effect | 3/3 | 3.0 | $0.00087 | create_test_ticket, search_corpus | - |
| f06 | side_effect | 3/3 | 2.0 | $0.00054 | search_corpus | - |
| f07 | side_effect | 3/3 | 3.0 | $0.00114 | create_test_ticket, search_corpus | - |
| g01 | access | 3/3 | 2.0 | $0.00047 | get_test_case | - |
| g02 | access | 3/3 | 2.0 | $0.00046 | list_test_cases | - |
| g03 | tracker | 3/3 | 2.0 | $0.00048 | get_test_case | - |
| g04 | tracker | 3/3 | 2.0 | $0.00050 | list_test_cases | - |
| g07 | tracker | 3/3 | 2.0 | $0.00050 | list_test_cases | - |
| g05 | tracker | 3/3 | 2.0 | $0.00044 | get_test_case | - |
| g06 | fault | 3/3 | 2.0 | $0.00047 | get_test_case | - |
