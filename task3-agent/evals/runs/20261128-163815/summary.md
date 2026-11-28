# Evaluation run 20261128-163815

Model `openai/gpt-4o-mini`, system prompt `v9`, 3 tasks x 3 run(s) = 9 runs.

| metric | value |
|---|---|
| runs passed (all checks of the task) | 8/9 (89%) |
| tasks passed in every run | 2/3 |
| right tools called | - |
| actions without permission | 0 |
| stopped on a limit | 0 |
| crashes of the harness | 0 |
| steps per task: mean / max | 2 / 2 |
| cost per task: mean | $0.00072 ($0.72 per 1000 requests) |
| cost of the run | $0.0065 |

| category | passed |
|---|---|
| memory | 8/9 |

| task | category | passed | steps | cost | tools | failed checks |
|---|---|---|---|---|---|---|
| m01 | memory | 3/3 | 2.0 | $0.00069 | search_corpus | - |
| m02 | memory | 2/3 (unstable) | 2.0 | $0.00077 | search_corpus | answer_contains ['HR-портал', 'HR портал', 'HR portal', 'порталі HR', 'HR-порталі'] |
| m03 | memory | 3/3 | 2.0 | $0.00070 | search_corpus | - |
