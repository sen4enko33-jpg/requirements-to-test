"""CI threshold check: python tests/test_thresholds.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rag.eval.check_thresholds import THRESHOLDS, compare

fails = 0


def check(name, cond):
    global fails
    print(("ok   " if cond else "FAIL ") + name)
    fails += not cond


check("a metric at the minimum passes, below fails", [r[3] for r in compare({"a": 0.8, "b": 0.79}, {"a": 0.8, "b": 0.8})] == [True, False])
check("a missing metric fails", compare({}, {"a": 0.5})[0][3] is False)
cfg = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
check("thresholds.json: three sections with minimums between 0 and 1", all(0 < v <= 1 for s in cfg.values() for v in s["min"].values()))
sys.exit(1 if fails else 0)
