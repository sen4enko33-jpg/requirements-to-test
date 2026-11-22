"""Trace of one request: every event (start, model call, tool call, stop) is one JSON line.

The file is written line by line, so a crash still leaves the steps before it. Tests and evaluations read the trace to
check what the agent did (which tools, how many steps, why it stopped), not only the text of the answer."""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path


class Trace:
    def __init__(self, directory: str | Path | None = None, run_id: str | None = None):
        self.run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.events: list[dict] = []
        self.path: Path | None = None
        self._t0 = time.monotonic()
        if directory is not None:
            Path(directory).mkdir(parents=True, exist_ok=True)
            self.path = Path(directory) / f"{self.run_id}.jsonl"

    def log(self, event: str, **data) -> dict:
        rec = {"run_id": self.run_id, "t": round(time.monotonic() - self._t0, 3), "event": event, **data}
        self.events.append(rec)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return rec

    def of(self, event: str) -> list[dict]:
        return [e for e in self.events if e["event"] == event]

    @staticmethod
    def read(path: str | Path) -> list[dict]:
        return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
