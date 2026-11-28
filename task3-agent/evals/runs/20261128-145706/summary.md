# Evaluation run 20261128-145706

Model `openai/gpt-4o-mini`, system prompt `v6`, 1 tasks x 3 run(s) = 3 runs.

| metric | value |
|---|---|
| runs passed (all checks of the task) | 0/3 (0%) |
| tasks passed in every run | 0/1 |
| right tools called (runs with tool checks) | 0% of 3 |
| actions without permission | 0 |
| stopped on a limit | 0 |
| crashes of the harness | 0 |
| steps per task: mean / max | 1 / 1 |
| cost per task: mean | $0.00023 ($0.23 per 1000 requests) |
| cost of the run | $0.0007 |

| category | passed |
|---|---|
| tracker | 0/3 |

| task | category | passed | steps | cost | tools | failed checks |
|---|---|---|---|---|---|---|
| g07 | tracker | 0/3 | 1.0 | $0.00023 | - | answer_contains ['TC-0003']<br>answer_contains ['TC-0004']<br>tools_required list_test_cases (called: []) |
