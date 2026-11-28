# Evaluation run 20261128-164032

Model `openai/gpt-4o-mini`, system prompt `v9`, 3 tasks x 3 run(s) = 9 runs.

| metric | value |
|---|---|
| runs passed (all checks of the task) | 9/9 (100%) |
| tasks passed in every run | 3/3 |
| right tools called | - |
| actions without permission | 0 |
| stopped on a limit | 0 |
| crashes of the harness | 0 |
| steps per task: mean / max | 2 / 2 |
| cost per task: mean | $0.00069 ($0.69 per 1000 requests) |
| cost of the run | $0.0062 |

| category | passed |
|---|---|
| memory | 9/9 |

| task | category | passed | steps | cost | tools | failed checks |
|---|---|---|---|---|---|---|
| m01 | memory | 3/3 | 2.0 | $0.00059 | search_corpus | - |
| m02 | memory | 3/3 | 2.0 | $0.00088 | search_corpus | - |
| m03 | memory | 3/3 | 2.0 | $0.00060 | search_corpus | - |
