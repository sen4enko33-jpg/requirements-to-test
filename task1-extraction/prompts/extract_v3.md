You are an assistant that converts a raw fragment of a software requirements document into structured JSON.

## Task

Read the document excerpt below and extract its content according to the schema you are given. Fill every field as defined in "Field definitions" below.

The excerpt is raw text cut out of a PDF. It may contain page headers, page numbers, broken line wrapping, typos, missing words, and sentences in a different language (for example Ukrainian inside an English document). Work with the text as it is.

## Rules

1. One requirement per complete statement that describes an obligation or behavior of the system. If a statement contains a list of items under a single "shall", keep it as one requirement.
2. Do not extract headings, page headers or numbers, document metadata, priorities, diagram labels, or text marked as deleted.
3. Copy the requirement text exactly as it is written in the source, including its wording, typos and original language. Do not paraphrase, shorten, translate or merge statements. Remove only layout artifacts: list numbers and bullets, page headers and page numbers, and line breaks inside a sentence.
4. Extract requirements written in any language present in the excerpt.
5. Use only information present in the excerpt; never guess. Use null (or an empty list) when a value is not stated: no id given, no heading above the requirement, no title visible.
6. In `actors`, list only users, roles and external systems; do not include the system being specified.
7. Keep the order of the requirements as in the source.
8. `section`: build it only from heading titles printed in the excerpt, as "parent heading > nearest heading above the requirement" (at most two levels; one title if there is no parent heading), with section numbers removed. Never use a bare number as the section. Example: for "3.2.1 Unicast Communication" under "3.2 Specific Requirement" write `Specific Requirement > Unicast Communication`, not `3.2.1`. If no heading title is printed above the requirement, use null.
9. List every requirement once. Never repeat a statement that is already in your list, and stop when you reach the end of the excerpt. Statements that differ in even one detail (another level, value or actor) are different requirements.

## Field definitions

- `doc_title`: Document title if present in the excerpt; otherwise null
- `domain`: Application domain of the system; 'other' if none fits
- `language`: Language of the excerpt: en, uk, or mixed if both are present
- `actors`: Users, roles or external systems that interact with the system
- `requirements`: All requirements found in the excerpt. Each has:
  - `id`: Requirement identifier as written in the text (e.g. 'REQ-12'); null if absent
  - `section`: Heading path of the block the requirement belongs to: the title of its parent heading and of its nearest heading above it, as they appear in the excerpt, without section numbers, joined with ' > ' (e.g. 'Projection Object > Update'). At most two levels; only the nearest heading if it has no parent heading in the excerpt. null if no heading is printed above the requirement in the excerpt
  - `text`: The requirement statement, copied from the source exactly as written; only layout artifacts (numbering, page headers, line breaks) are removed
  - `type`: functional: what the system does; non_functional: quality attribute (performance, security, usability); constraint: imposed limit (technology, law, standard); interface: interaction with users or external systems
  - `testable`: yes: a test can be derived directly; partial: needs clarification; no: too vague to test
- `has_acceptance_criteria`: True if the excerpt contains explicit acceptance criteria
- `open_questions`: Items the text itself marks as unresolved: explicit questions, TODO or placeholder notes (e.g. 'Specify required archive structure', 'How is X specified?'), copied or minimally rephrased; do not add your own analysis; empty list if the text marks none

## Document excerpt

<<DOCUMENT>>
