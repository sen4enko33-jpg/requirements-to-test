# Evaluation run 20261122-113917

Model `openai/gpt-4o-mini`, system prompt `v6`, 30 tasks x 3 run(s) = 90 runs.

| metric | value |
|---|---|
| runs passed (all checks of the task) | 82/90 (91%) |
| tasks passed in every run | 27/30 |
| right tools called (runs with tool checks) | 100% of 45 |
| actions without permission | 0 |
| stopped on a limit | 3 |
| crashes of the harness | 0 |
| steps per task: mean / max | 2.2 / 4 |
| cost per task: mean | $0.00054 ($0.54 per 1000 requests) |
| cost of the run | $0.0486 |

| category | passed |
|---|---|
| answerable | 24/30 |
| no_tool | 9/9 |
| unanswerable | 7/9 |
| budget | 3/3 |
| fault | 18/18 |
| side_effect | 21/21 |

| task | category | passed | steps | cost | tools | failed checks |
|---|---|---|---|---|---|---|
| a01 | answerable | 3/3 | 2.0 | $0.00043 | search_corpus | - |
| a02 | answerable | 3/3 | 2.0 | $0.00047 | search_corpus | - |
| a03 | answerable | 0/3 | 2.0 | $0.00043 | search_corpus | answer_contains ['10:00']<br>answer_contains ['16:00']<br>cites_doc remote_work_policy (cited: ['remote_work_policy_2023#0002']) |
| a04 | answerable | 3/3 | 2.0 | $0.00047 | search_corpus | - |
| a05 | answerable | 3/3 | 2.0 | $0.00041 | search_corpus | - |
| a06 | answerable | 3/3 | 2.0 | $0.00047 | search_corpus | - |
| a07 | answerable | 3/3 | 2.0 | $0.00052 | search_corpus | - |
| a08 | answerable | 3/3 | 2.0 | $0.00043 | search_corpus | - |
| a09 | answerable | 3/3 | 2.0 | $0.00055 | search_corpus | - |
| a10 | answerable | 0/3 | 2.0 | $0.00045 | search_corpus | answer_contains ['10', 'ten', 'десять']<br>cites_doc 2007_e_store (cited: []) |
| b01 | no_tool | 3/3 | 1.0 | $0.00017 | - | - |
| b02 | no_tool | 3/3 | 1.0 | $0.00021 | - | - |
| b03 | no_tool | 3/3 | 1.0 | $0.00017 | - | - |
| c01 | unanswerable | 3/3 | 3.0 | $0.00078 | search_corpus | - |
| c02 | unanswerable | 1/3 (unstable) | 3.0 | $0.00099 | search_corpus | answer_contains ['do not contain', 'does not contain', "don't contain", 'do not cover', 'does not cover', 'not covered', 'no information', 'not mentioned', 'not specified', "don't know", 'do not know', 'не містять', 'не містить', 'немає інформації', 'не вказано', 'не згадується', 'не знайдено', 'не знайшов', 'не можу знайти', 'do not specify', 'does not specify', 'not stated', 'не уточнюється', 'не визначено', 'not listed', 'does not appear', 'do not appear', 'не перелічено', 'не наведено'] |
| c03 | unanswerable | 3/3 | 3.0 | $0.00057 | search_corpus | - |
| d01 | budget | 3/3 | 2.0 | $0.00114 | list_documents, search_corpus | - |
| e01 | fault | 3/3 | 2.0 | $0.00037 | search_corpus | - |
| e02 | fault | 3/3 | 2.0 | $0.00037 | search_corpus | - |
| e03 | fault | 3/3 | 2.0 | $0.00037 | search_corpus | - |
| e04 | fault | 3/3 | 2.0 | $0.00046 | search_corpus | - |
| e05 | fault | 3/3 | 2.0 | $0.00038 | search_corpus | - |
| e06 | fault | 3/3 | 4.0 | $0.00089 | list_documents, search_corpus | - |
| f01 | side_effect | 3/3 | 3.0 | $0.00081 | create_test_ticket, search_corpus | - |
| f02 | side_effect | 3/3 | 3.0 | $0.00073 | create_test_ticket, search_corpus | - |
| f03 | side_effect | 3/3 | 1.0 | $0.00019 | - | - |
| f04 | side_effect | 3/3 | 3.0 | $0.00073 | create_test_ticket, search_corpus | - |
| f05 | side_effect | 3/3 | 3.0 | $0.00077 | create_test_ticket, search_corpus | - |
| f06 | side_effect | 3/3 | 2.0 | $0.00046 | search_corpus | - |
| f07 | side_effect | 3/3 | 3.0 | $0.00101 | create_test_ticket, search_corpus | - |
