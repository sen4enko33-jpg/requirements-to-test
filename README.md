# requirements-to-test

Extract structured requirements from messy text excerpts (taken from PURE requirements
documents) using a schema, and compare a paid cloud model with a local model:
field-level accuracy, response validity, latency, and cost.

## Structure
- `data/texts` — text excerpts used for runs (001.txt …)
- `data/golden` — manually labeled ground truth
- `src/` — schema, model clients, validation, metrics
- `prompts/` — prompt versions and CHANGELOG
- `results/` — run logs (jsonl)
- `report/` — final comparison

## Setup
TODO

## Usage
TODO
