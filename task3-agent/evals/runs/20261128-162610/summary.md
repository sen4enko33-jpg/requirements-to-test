# Evaluation run 20261128-162610

Model `openai/gpt-4o-mini`, system prompt `v9`, 8 tasks x 3 run(s) = 24 runs.

| metric | value |
|---|---|
| runs passed (all checks of the task) | 24/24 (100%) |
| tasks passed in every run | 8/8 |
| right tools called (runs with tool checks) | 100% of 3 |
| actions without permission | 0 |
| stopped on a limit | 0 |
| crashes of the harness | 0 |
| steps per task: mean / max | 2.25 / 3 |
| cost per task: mean | $0.00067 ($0.67 per 1000 requests) |
| cost of the run | $0.0160 |

| category | passed |
|---|---|
| answerable | 12/12 |
| versions | 12/12 |

| task | category | passed | steps | cost | tools | failed checks |
|---|---|---|---|---|---|---|
| a01 | answerable | 3/3 | 2.0 | $0.00065 | search_corpus | - |
| a03 | answerable | 3/3 | 3.0 | $0.00086 | search_corpus | - |
| a04 | answerable | 3/3 | 2.0 | $0.00061 | search_corpus | - |
| a08 | answerable | 3/3 | 2.0 | $0.00057 | search_corpus | - |
| v01 | versions | 3/3 | 2.0 | $0.00062 | search_corpus | - |
| v02 | versions | 3/3 | 2.0 | $0.00057 | search_corpus | - |
| v03 | versions | 3/3 | 2.0 | $0.00064 | search_corpus | - |
| v04 | versions | 3/3 | 3.0 | $0.00081 | search_corpus | - |
