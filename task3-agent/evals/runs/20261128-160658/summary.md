# Evaluation run 20261128-160658

Model `openai/gpt-4o-mini`, system prompt `v7`, 2 tasks x 3 run(s) = 6 runs.

| metric | value |
|---|---|
| runs passed (all checks of the task) | 4/6 (67%) |
| tasks passed in every run | 1/2 |
| right tools called (runs with tool checks) | 67% of 6 |
| actions without permission | 0 |
| stopped on a limit | 0 |
| crashes of the harness | 0 |
| steps per task: mean / max | 3.67 / 6 |
| cost per task: mean | $0.00173 ($1.73 per 1000 requests) |
| cost of the run | $0.0104 |

| category | passed |
|---|---|
| answerable | 3/3 |
| unanswerable | 1/3 |

| task | category | passed | steps | cost | tools | failed checks |
|---|---|---|---|---|---|---|
| a02 | answerable | 3/3 | 2.0 | $0.00064 | search_corpus | - |
| c02 | unanswerable | 1/3 (unstable) | 5.3 | $0.00282 | search_corpus | answer_contains ['do not contain', 'does not contain', "don't contain", 'do not cover', 'does not cover', 'not covered', 'no information', 'not mentioned', 'not specified', "don't know", 'do not know', 'не містять', 'не містить', 'немає інформації', 'не вказано', 'не згадується', 'не знайдено', 'не знайшов', 'не можу знайти', 'do not specify', 'does not specify', 'not stated', 'не уточнюється', 'не визначено', 'not listed', 'does not appear', 'do not appear', 'не перелічено', 'не наведено', 'not found', 'not explicitly found']<br>tool_calls_max 3 (5 calls) |
