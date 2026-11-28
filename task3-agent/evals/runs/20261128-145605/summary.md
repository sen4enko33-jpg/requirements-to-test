# Evaluation run 20261128-145605

Model `openai/gpt-4o-mini`, system prompt `v6`, 6 tasks x 3 run(s) = 18 runs.

| metric | value |
|---|---|
| runs passed (all checks of the task) | 18/18 (100%) |
| tasks passed in every run | 6/6 |
| right tools called (runs with tool checks) | 100% of 18 |
| actions without permission | 0 |
| stopped on a limit | 0 |
| crashes of the harness | 0 |
| steps per task: mean / max | 2 / 2 |
| cost per task: mean | $0.00045 ($0.45 per 1000 requests) |
| cost of the run | $0.0080 |

| category | passed |
|---|---|
| access | 6/6 |
| tracker | 9/9 |
| fault | 3/3 |

| task | category | passed | steps | cost | tools | failed checks |
|---|---|---|---|---|---|---|
| g01 | access | 3/3 | 2.0 | $0.00042 | get_test_case | - |
| g02 | access | 3/3 | 2.0 | $0.00042 | list_test_cases | - |
| g03 | tracker | 3/3 | 2.0 | $0.00046 | get_test_case | - |
| g04 | tracker | 3/3 | 2.0 | $0.00050 | list_test_cases | - |
| g05 | tracker | 3/3 | 2.0 | $0.00042 | get_test_case | - |
| g06 | fault | 3/3 | 2.0 | $0.00046 | get_test_case | - |
