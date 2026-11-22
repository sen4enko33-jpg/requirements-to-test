"""State of one agent request that the tools share: which passages the agent has seen.

create_test_ticket accepts only a requirement the agent actually read in this conversation (returned by search_corpus or
get_passage), so a test case cannot be filed against a ref the model invented or remembered."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Session:
    run_id: str | None = None
    request: str | None = None             # the user's message: part of the idempotency key of create_test_ticket
    seen_refs: set[str] = field(default_factory=set)

    def saw(self, refs) -> None:
        self.seen_refs.update(refs)
