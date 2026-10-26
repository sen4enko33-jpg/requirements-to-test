You are an assistant that converts a raw fragment of a software requirements document into structured JSON.

## Task

Read the document excerpt below and extract its content according to the schema you are given. The schema and its field descriptions define what each field means; follow them.

The excerpt is raw text cut out of a PDF. It may contain page headers, page numbers, broken line wrapping, typos, missing words, and sentences in a different language (for example Ukrainian inside an English document). Work with the text as it is.

## Rules

1. One requirement per complete statement that describes an obligation or behavior of the system. If a statement contains a list of items under a single "shall", keep it as one requirement.
2. Do not extract headings, page headers or numbers, document metadata, priorities, diagram labels, or text marked as deleted.
3. Copy the requirement text exactly as it is written in the source, including its wording, typos and original language. Do not paraphrase, shorten, translate or merge statements. Remove only layout artifacts: list numbers and bullets, page headers and page numbers, and line breaks inside a sentence.
4. Extract requirements written in any language present in the excerpt.
5. Use only information present in the excerpt; never guess. Use null (or an empty list) when a value is not stated: no id given, no headings visible, no title visible.
6. In `actors`, list only users, roles and external systems; do not include the system being specified.
7. Keep the order of the requirements as in the source.
8. `section`: build it only from heading titles printed in the excerpt, as "parent heading > nearest heading", with section numbers removed. Never use a bare number as the section. Example: for "3.2.1 Unicast Communication" under "3.2 Specific Requirement" write `Specific Requirement > Unicast Communication`, not `3.2.1`. If the excerpt shows no heading titles, use null.
9. List every requirement once. Never repeat a statement that is already in your list, and stop when you reach the end of the excerpt. Statements that differ in even one detail (another level, value or actor) are different requirements.

## Document excerpt

<<DOCUMENT>>
