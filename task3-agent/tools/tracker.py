"""A small test-case tracker in SQLite: the "outside world" that the agent can change (step 1.4).

Idempotency: every test case has an idempotency key. The caller passes it (the agent derives it from the user's request
and the requirement, see tools/ticket_tool.py); without one the key is a hash of (document, requirement ref, title) after
normalisation (case, spaces). The column is UNIQUE, so creating the same test case again - a repeated request, a retry
after a lost answer, the model calling the tool twice - returns the existing row with created=False instead of a duplicate. The check
is done by the database in one statement (INSERT ... ON CONFLICT DO NOTHING), not by a read-then-write in Python, so two
calls at the same time cannot both insert."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(os.environ.get("TRACKER_DB", Path(__file__).resolve().parents[1] / "data" / "tracker.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS test_cases (
    id               INTEGER PRIMARY KEY,    -- no AUTOINCREMENT: it burns a number on every rejected duplicate (TC-0001, TC-0003)
    idempotency_key  TEXT NOT NULL UNIQUE,
    doc_id           TEXT NOT NULL,
    requirement_ref  TEXT NOT NULL,
    title            TEXT NOT NULL,
    steps            TEXT NOT NULL,          -- JSON list of strings
    expected         TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    run_id           TEXT                    -- the agent request that created it (for the trace)
)
"""


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def idempotency_key(*parts: str) -> str:
    """A stable key of the parts after normalisation (case, spaces): the same parts = the same test case."""
    raw = "\x1f".join(_norm(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class Tracker:
    def __init__(self, path: str | Path | None = None):
        """path: SQLite file (created with its folder); ":memory:" for tests."""
        self.path = str(path or DEFAULT_DB)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: tools run in a worker thread (see registry); sqlite3 serialises the writes
        self._db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute(SCHEMA)

    @staticmethod
    def _row(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["steps"] = json.loads(d["steps"])
        d["ticket"] = f"TC-{d['id']:04d}"
        return d

    def create(self, doc_id: str, requirement_ref: str, title: str, steps: list[str], expected: str,
               run_id: str | None = None, key: str | None = None) -> tuple[dict, bool]:
        """-> (the test case, created). created=False: it existed already (same idempotency key), nothing was written.
        key: the idempotency key; None = a hash of (doc_id, requirement_ref, title)."""
        key = key or idempotency_key(doc_id, requirement_ref, title)
        cur = self._db.execute(
            "INSERT INTO test_cases (idempotency_key, doc_id, requirement_ref, title, steps, expected, created_at, run_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(idempotency_key) DO NOTHING",
            (key, doc_id, requirement_ref, title.strip(), json.dumps(steps, ensure_ascii=False), expected.strip(),
             datetime.now(timezone.utc).isoformat(timespec="seconds"), run_id))
        created = cur.rowcount == 1
        row = self._db.execute("SELECT * FROM test_cases WHERE idempotency_key = ?", (key,)).fetchone()
        return self._row(row), created

    def get(self, ticket_id: int) -> dict | None:
        r = self._db.execute("SELECT * FROM test_cases WHERE id = ?", (ticket_id,)).fetchone()
        return self._row(r) if r else None

    def all(self) -> list[dict]:
        return [self._row(r) for r in self._db.execute("SELECT * FROM test_cases ORDER BY id")]

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM test_cases").fetchone()[0]

    def close(self) -> None:
        self._db.close()
