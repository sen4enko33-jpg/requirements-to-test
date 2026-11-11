## Quality (golden set: 10 excerpts, 158 gold requirements)

| model | sampling | prompt | doc_title | domain | language | acceptance | actors F1 | req. P | req. R | req. F1 | type | testable | id | section | section (last heading) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| llama3.2:3b | A | v1 | 50% | 10% | 70% | 50% | 0.58 | 0.31 | 0.20 | 0.24 | 13% | 16% | 15% | 3% | 6% |
| llama3.2:3b | B | v1 | 50% | 20% | 70% | 70% | 0.62 | 0.15 | 0.11 | 0.13 | 11% | 6% | 7% | 3% | 7% |
| llama3.2:3b | A | v2 | 40% | 10% | 70% | 30% | 0.51 | 0.31 | 0.28 | 0.30 | 17% | 24% | 20% | 1% | 14% |
| llama3.2:3b | B | v2 | 30% | 20% | 70% | 40% | 0.59 | 0.29 | 0.16 | 0.20 | 11% | 14% | 3% | 3% | 4% |
| openai/gpt-4o-mini | A | v1 | 50% | 90% | 90% | 100% | 0.85 | 0.61 | 0.69 | 0.65 | 56% | 58% | 54% | 9% | 54% |
| openai/gpt-4o-mini | B | v1 | 50% | 90% | 90% | 100% | 0.85 | 0.57 | 0.66 | 0.61 | 51% | 55% | 58% | 6% | 44% |
| openai/gpt-4o-mini | A | v2 | 50% | 100% | 90% | 100% | 0.85 | 0.58 | 0.73 | 0.65 | 60% | 63% | 59% | 20% | 60% |
| openai/gpt-4o-mini | B | v2 | 50% | 100% | 80% | 100% | 0.85 | 0.62 | 0.72 | 0.66 | 58% | 61% | 57% | 17% | 54% |

## Reliability, speed, cost (all 31 excerpts)

| model | sampling | prompt | valid % | partial % | copy viol. % | empty % | capped % | p50 s | p95 s | USD / 1000 docs |
|---|---|---|---|---|---|---|---|---|---|---|
| llama3.2:3b | A | v1 | 94% | 19% | 16.0% | 13% | 19% | 22.3 | 80.4 | 0.00 USD |
| llama3.2:3b | B | v1 | 97% | 35% | 9.3% | 3% | 13% | 31.6 | 99.0 | 0.00 USD |
| llama3.2:3b | A | v2 | 100% | 48% | 10.2% | 10% | 23% | 42.4 | 122.6 | 0.00 USD |
| llama3.2:3b | B | v2 | 97% | 48% | 7.4% | 6% | 16% | 38.4 | 106.8 | 0.00 USD |
| openai/gpt-4o-mini | A | v1 | 100% | 0% | 0.0% | 0% | 0% | 9.4 | 19.8 | 0.80 USD |
| openai/gpt-4o-mini | B | v1 | 100% | 0% | 1.0% | 0% | 0% | 7.7 | 14.2 | 0.75 USD |
| openai/gpt-4o-mini | A | v2 | 100% | 13% | 1.9% | 0% | 0% | 11.0 | 28.2 | 0.99 USD |
| openai/gpt-4o-mini | B | v2 | 100% | 6% | 1.4% | 0% | 0% | 11.3 | 26.7 | 0.90 USD |
