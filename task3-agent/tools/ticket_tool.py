"""create_test_ticket: the one tool with a side effect. It writes a test case to the tracker (tools/tracker.py).

It is marked side_effect=True and safe=False: the registry never retries it, and (sub-step 1.4.3) the agent loop runs it
only after a human confirmed the call in code. Protection against guessing: every argument is required, and the requirement
must be a passage the agent read in this conversation (Session.seen_refs)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from . import descriptions
from .corpus import Corpus
from .corpus_tools import REF_PATTERN
from .registry import Tool, ToolInputError
from .session import Session
from .tracker import Tracker, idempotency_key


class TicketArgs(BaseModel):
    requirement_ref: str = Field(pattern=REF_PATTERN, description="Ref of the passage with the requirement (from search_corpus).")
    title: str = Field(min_length=5, max_length=120, description="Short name of the test case.")
    steps: list[str] = Field(min_length=1, max_length=10, description="Actions of the tester, in order.")
    expected: str = Field(min_length=5, max_length=500, description="Expected result, taken from the requirement text.")

    @field_validator("steps")
    @classmethod
    def _steps(cls, v: list[str]) -> list[str]:
        steps = [s.strip() for s in v]
        if any(len(s) < 3 for s in steps):
            raise ValueError("every step needs at least 3 characters")
        return steps


class TicketOutput(BaseModel):
    ticket: str = Field(pattern=r"^TC-\d{4,}$")
    created: bool
    duplicate: bool
    doc_id: str
    requirement_ref: str
    title: str


def make_ticket_tool(tracker: Tracker, corpus: Corpus, session: Session) -> Tool:
    def precheck(a: TicketArgs) -> None:
        """Runs before the person is asked: nobody should be asked to approve a test case for an invented requirement."""
        if a.requirement_ref not in corpus.chunks:
            raise ToolInputError(f"unknown requirement_ref {a.requirement_ref!r}; find the requirement with search_corpus")
        if a.requirement_ref not in session.seen_refs:
            raise ToolInputError(f"requirement_ref {a.requirement_ref!r} was not returned by search_corpus or get_passage in "
                                 "this conversation; search for the requirement first and use a ref from the results")

    def create_test_ticket(a: TicketArgs) -> dict:
        chunk = corpus.chunks[a.requirement_ref]
        # The key comes from what the USER asked (their message) and which requirement, not from the title: the model writes
        # another title on every run ("Test Maximum Remote Work Days", then "Maximum Remote Work Days Test Case"), so a
        # title-based key let a repeated request create a duplicate in the real runs of step 1.4.4.
        key = idempotency_key("request", a.requirement_ref, session.request) if session.request else None
        tc, created = tracker.create(chunk["doc_id"], a.requirement_ref, a.title, a.steps, a.expected, session.run_id, key)
        return {"ticket": tc["ticket"], "created": created, "duplicate": not created, "doc_id": tc["doc_id"],
                "requirement_ref": tc["requirement_ref"], "title": tc["title"]}

    name = "create_test_ticket"
    return Tool(name, descriptions.description(name), TicketArgs, create_test_ticket, safe=False, side_effect=True,
                version=descriptions.version(name), output_model=TicketOutput, precheck=precheck)
