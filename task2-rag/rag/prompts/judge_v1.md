You grade answers of a question-answering system that answers only from document passages. Give two verdicts.

You get: the question, the REFERENCE (what a correct answer says, written by a human), the SYSTEM ANSWER, and the CITED PASSAGES
(the only text the system was allowed to cite). Judge only from these; use no outside knowledge.

correct - does the system answer agree with the reference on what the question asks?
- Extra true detail is fine. A different number, name, date or version than the reference is NOT correct, even when the rest is right.
- If the question names no version or year and the reference gives the current value, the answer is correct only when the current value
  is the one it gives as its answer; an older value may be mentioned after it, but not put first or presented as the answer.
- If the reference says the documents do not contain the answer, the answer is correct only when it says it does not know or that the
  documents do not say it. An answer that guesses or states a fact is not correct.
- If the reference has an answer and the system says it does not know, it is not correct.

faithful - is every factual statement of the system answer supported by the cited passages?
- A statement that is not in the cited passages (or is only in other passages), or a factual answer that cites nothing, is not faithful,
  even when the statement is true.
- "I don't know" that makes no factual claim is faithful.

Reply as JSON: {"correct": true|false, "faithful": true|false, "reason": "<one short sentence for each verdict>"}

Question: <<QUESTION>>

REFERENCE: <<REFERENCE>>

SYSTEM ANSWER: <<ANSWER>>

CITED PASSAGES:
<<PASSAGES>>
