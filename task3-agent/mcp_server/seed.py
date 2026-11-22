"""Demo rows of OTHER teams in the tracker, so that the access rules have something to deny:
    python -m mcp_server.seed [--db PATH]

The rows are fictional test cases of the team payments-qa for the E-Store requirements. Running it again adds nothing
(fixed idempotency keys). The test cases of our own team (hr-policy-qa) are created by the agent."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.tracker import DEFAULT_DB, Tracker  # noqa: E402

SEED = [
    {"team": "payments-qa", "doc_id": "2007_e_store", "requirement_ref": "2007_e_store#0008",
     "title": "Search shows at most 10 results per screen",
     "steps": ["Search for a term with more than 10 matching products", "Count the results on the first screen"],
     "expected": "Exactly 10 results are shown; the user can move to the next results."},
    {"team": "payments-qa", "doc_id": "2007_e_store", "requirement_ref": "2007_e_store#0012",
     "title": "Shipping options come from the shipping department",
     "steps": ["Put a product into the cart", "Open the checkout", "Look at the shipping methods"],
     "expected": "All shipping options of the shipping department are listed and one can be selected."},
]


def seed(tracker: Tracker) -> int:
    added = 0
    for row in SEED:
        _, created = tracker.create(row["doc_id"], row["requirement_ref"], row["title"], row["steps"], row["expected"],
                                    run_id="seed", key=f"seed:{row['team']}:{row['requirement_ref']}", team=row["team"])
        added += created
    return added


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    a = ap.parse_args()
    t = Tracker(a.db)
    print(f"{seed(t)} seed rows added, {t.count()} rows in {a.db}")


if __name__ == "__main__":
    main()
