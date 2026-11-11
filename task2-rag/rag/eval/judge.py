"""LLM judge of the answers: two verdicts per answer, correct (against the reference answer) and faithful (against the cited
passages). The prompt is rag/prompts/judge_<version>.md; the judge model is models.judge in config.yaml (not the answering model).
The judge is checked against hand-rated answers in rag/eval/calibrate.py."""
import json
import re
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
JUDGE_VERSION = "v2"
CHUNKS = Path(__file__).resolve().parents[1] / "data" / "chunks.jsonl"
SAMPLING = {"temperature": 0.0, "top_p": 1.0}


class Verdict(BaseModel):
    correct: bool = Field(description="The answer agrees with the reference on what the question asks.")
    faithful: bool = Field(description="Every factual statement is supported by the cited passages.")
    reason: str = Field(description="One short sentence for each verdict.")


_chunks: dict | None = None


def chunk_text(chunk_id: str) -> str:
    global _chunks
    if _chunks is None:
        _chunks = {c["chunk_id"]: c["text"] for c in map(json.loads, CHUNKS.read_text(encoding="utf-8").splitlines())}
    return _chunks[chunk_id]


def passages_text(citations: list[dict], limit: int = 1500) -> str:
    """The cited passages, numbered as in the answer; a long passage is cut to `limit` characters."""
    out = [f"[{c['n']}] ({c['doc_id']}, {c.get('date') or c.get('year')}) {chunk_text(c['chunk_id']).strip()[:limit]}" for c in citations]
    return "\n\n".join(out) or "(the answer cites no passage)"


def build_prompt(question: str, reference: str, answer: str, passages: str, version: str = JUDGE_VERSION) -> str:
    values = {"QUESTION": question.strip(), "REFERENCE": reference.strip(), "ANSWER": answer.strip(), "PASSAGES": passages.strip()}
    return re.sub(r"<<(QUESTION|REFERENCE|ANSWER|PASSAGES)>>", lambda m: values[m.group(1)], (PROMPTS / f"judge_{version}.md").read_text(encoding="utf-8"))


def judge(llm, question: str, reference: str, answer: str, citations: list[dict], version: str = JUDGE_VERSION) -> dict:
    """{"correct", "faithful", "reason"}; on a model failure: {"error": ...}. One repeat when the JSON is invalid."""
    prompt = build_prompt(question, reference, answer, passages_text(citations), version)
    res = None
    for attempt in range(2):
        res = llm.generate(prompt if attempt == 0 else prompt + "\n\nReply with valid JSON only.", Verdict, SAMPLING)
        if not res.text:
            break
        try:
            return Verdict.model_validate_json(res.text).model_dump()
        except ValidationError:
            continue
    return {"error": (res.error if res else None) or "output is not valid JSON"}
