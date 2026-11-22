"""Checks of the test-case tracker and its idempotency (no network): python tests/test_tracker.py"""
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.tracker import Tracker, idempotency_key

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


ARGS = dict(doc_id="remote_work_policy", requirement_ref="remote_work_policy#0000", title="Remote days limit after probation",
            steps=["Log in as an employee after probation", "Request a third remote day in one week"],
            expected="The third day is rejected: at most two remote days per week.")

# --- create and read back
t = Tracker(":memory:")
tc, created = t.create(**ARGS, run_id="run-1")
check("create: a new test case is created", created and t.count() == 1)
check("create: readable ticket id TC-0001 and all fields stored",
      tc["ticket"] == "TC-0001" and tc["steps"] == ARGS["steps"] and tc["run_id"] == "run-1" and tc["created_at"])
check("get: by id", t.get(tc["id"])["title"] == ARGS["title"] and t.get(999) is None)

# --- idempotency
again, created2 = t.create(**ARGS, run_id="run-2")
check("same call again: no duplicate, the existing test case comes back",
      not created2 and t.count() == 1 and again["id"] == tc["id"] and again["run_id"] == "run-1")
variant = {**ARGS, "title": "  REMOTE days   limit after PROBATION ", "steps": ["other steps"]}
same, created3 = t.create(**variant)
check("same test case with other case/spaces in the title: still no duplicate", not created3 and same["id"] == tc["id"])
check("the first version is kept, a repeat does not overwrite it", t.get(tc["id"])["steps"] == ARGS["steps"])
other, created4 = t.create(**{**ARGS, "title": "Remote work needs the VPN"})
check("another title: a new test case", created4 and t.count() == 2 and other["ticket"] == "TC-0002")
other_req, created5 = t.create(**{**ARGS, "requirement_ref": "remote_work_policy#0002"})
check("same title for another requirement: a new test case", created5 and t.count() == 3)

check("key: stable and normalised",
      idempotency_key("A", "a#0001", " Title  x") == idempotency_key("a", "A#0001", "title x")
      and idempotency_key("a", "a#0001", "t1") != idempotency_key("a", "a#0001", "t2"))

# --- teams
check("team: the default team is stored", tc["team"] == "hr-policy-qa")
pay, _ = t.create(**{**ARGS, "title": "Card is checked for fraud", "requirement_ref": "2007_e_store#0010"}, team="payments-qa")
check("team: another team is stored on its row", pay["team"] == "payments-qa")

# --- a tracker.db of step 1.4 (no team column) is upgraded in place
import sqlite3
with tempfile.TemporaryDirectory() as d:
    old = Path(d) / "old.db"
    con = sqlite3.connect(old)
    con.execute("CREATE TABLE test_cases (id INTEGER PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, doc_id TEXT NOT NULL, "
                "requirement_ref TEXT NOT NULL, title TEXT NOT NULL, steps TEXT NOT NULL, expected TEXT NOT NULL, "
                "created_at TEXT NOT NULL, run_id TEXT)")
    con.execute("INSERT INTO test_cases VALUES (1, 'k', 'd', 'd#0001', 't', '[]', 'e', 'now', NULL)")
    con.commit(); con.close()
    up = Tracker(old)
    check("upgrade: the old row keeps its data and gets the default team", up.get(1)["team"] == "hr-policy-qa" and up.count() == 1)
    up.close()

# --- on disk: survives a restart (a repeated request in a new process)
with tempfile.TemporaryDirectory() as d:
    path = Path(d) / "sub" / "tracker.db"
    t1 = Tracker(path)
    first, _ = t1.create(**ARGS)
    t1.close()
    t2 = Tracker(path)
    second, created_again = t2.create(**ARGS)
    check("on disk: the folder is created and a repeat after a restart is not a duplicate",
          path.exists() and not created_again and second["id"] == first["id"] and t2.count() == 1)

    # --- two calls at the same moment (a retry racing the original): exactly one row
    results = []
    barrier = threading.Barrier(8)

    def worker():
        tr = Tracker(path)
        barrier.wait()
        results.append(tr.create(**{**ARGS, "title": "Concurrent case"})[1])
        tr.close()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    check("8 concurrent creates of one test case: exactly one is created", results.count(True) == 1 and t2.count() == 2)
    t2.close()

print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'all checks passed'}")
sys.exit(1 if FAILED else 0)
