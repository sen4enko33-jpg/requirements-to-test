# Prompt changelog

Prompts live in `prompts/extract_<version>.md`. The version is passed to `src/prompts.py` (`build_prompt("v1", text)`).
Each entry records what changed and why; results are added after the evaluation run.

## v1 (2026-10-14) — baseline

**What it is.** Minimal instruction prompt: role, task, seven general rules, the document placeholder. Field descriptions are not repeated here (they live in the schema). No examples, no edge-case handling.

**Design decisions.**
- Field descriptions live only in `Field(description=...)` in `src/schema.py`; the schema reaches the model through structured output (Anthropic `messages.parse(output_format=...)`, Ollama `format`). The prompt holds only what the schema cannot say: when to use null, what not to extract, copy-as-is rules.
- `text` of a requirement is copied from the source exactly as written, including typos; only layout artifacts (numbering, page headers, line breaks) are removed. The golden set keeps source typos in requirement text for the same reason.
- `open_questions` accepts only items the text itself marks as unresolved; `has_acceptance_criteria` is true only for explicit acceptance criteria.
- One requirement per complete statement; a list under a single "shall" stays one requirement.

**Known gaps (expected, not yet measured).** Granularity of use-case steps and event lists, handling of "Intentionally deleted" items and assumptions, `section` building when headings are partly cut off, ids given at section level, and sentences inserted in another language. These are the candidates for v2.

**Results.** _to be filled after the evaluation run_

<!-- Template for the next entry:

## v2 (date)

**What changed.** ...
**Why.** (which errors from the error analysis it targets)
**Results vs v1.** ...
-->
