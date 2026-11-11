"""Checks of the array limits (maxItems in the request), the removal of repeated requirements and the capped flag.

    python tests/test_limits.py
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.clients.base import GenResult, ModelClient  # noqa: E402
from src.clients.openai_compat import OpenAICompatClient  # noqa: E402
from src.run import run_doc  # noqa: E402
from src.schema import Extraction  # noqa: E402
from src.validate import check_copy, drop_repeats  # noqa: E402

DOC_ID = sorted(p.stem for p in (ROOT / "data" / "noisy").glob("*.txt"))[0]
SOURCE = (ROOT / "data" / "noisy" / f"{DOC_ID}.txt").read_text(encoding="utf-8")


def statements(n):
    words, out, i = SOURCE.split(), [], 0
    while len(out) < n and i + 10 <= len(words):
        cand = " ".join(words[i:i + 10])
        if not check_copy({"requirements": [{"text": cand}]}, SOURCE):
            out.append(cand)
            i += 40
        else:
            i += 1
    assert len(out) == n
    return out


def answer(*texts):
    return json.dumps({
        "doc_title": None, "domain": "other", "language": "en", "actors": ["user"],
        "requirements": [{"id": None, "section": None, "text": t, "type": "functional", "testable": "yes"} for t in texts],
        "has_acceptance_criteria": False, "open_questions": [],
    })


def check(name, condition):
    print(("ok   " if condition else "FAIL ") + name)
    if not condition:
        check.failed += 1
check.failed = 0


class Fake(ModelClient):
    name = "fake-model"

    def __init__(self, text, schema_limits=None):
        self.text, self.schema_limits, self.calls = text, schema_limits, 0

    def generate(self, prompt, response_model, sampling):
        self.calls += 1
        return GenResult(self.text, 1.0, 100, 50, 1, None, None)


def run(text, limits=None):
    client = Fake(text, limits)
    return client, run_doc(client, DOC_ID, "fake", "v1", "A", {"temperature": 0.0, "top_p": 1.0})


A, B, C = statements(3)

print("-- limits in the request")
sent = {}
def fake_create(**kw):
    sent.update(kw)
    msg = SimpleNamespace(content=answer(A), refusal=None)
    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, model_extra={}),
                           model_extra={}, choices=[SimpleNamespace(finish_reason="stop", message=msg)])
def make(limits):
    c = OpenAICompatClient("m", "http://localhost:1/v1", "k", 5, 1, schema_limits=limits)
    c._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    return c
make({"actors": 10, "open_questions": 7, "requirements": 40}).generate("p", Extraction, {"temperature": 0, "top_p": 1})
props = sent["response_format"]["json_schema"]["schema"]["properties"]
check("maxItems is added to actors, open_questions and requirements",
      props["actors"]["maxItems"] == 10 and props["open_questions"]["maxItems"] == 7 and props["requirements"]["maxItems"] == 40)
sent.clear()
make(None).generate("p", Extraction, {"temperature": 0, "top_p": 1})
props = sent["response_format"]["json_schema"]["schema"]["properties"]
check("without limits the request schema has no maxItems", all("maxItems" not in v for v in props.values()))
check("the Pydantic schema is not changed by the limits",
      "maxItems" not in json.dumps(Extraction.model_json_schema()))

print("-- repeated requirements")
ext = json.loads(answer(A, B, A.upper(), C, B))
out, removed = drop_repeats(ext)
check("repeats (same words, any case) are dropped, order kept",
      removed == 2 and [r["text"] for r in out["requirements"]] == [A, B, C])
out, removed = drop_repeats(json.loads(answer(A, B)))
check("no repeats: nothing removed", removed == 0 and len(out["requirements"]) == 2)
client, row = run(answer(A, B, A, A, B))
check("run_doc logs the number of removed repeats and keeps one of each",
      row["status"] == "ok" and row["n_duplicates_removed"] == 3 and row["copy_total"] == 2
      and [r["text"] for r in row["extraction"]["requirements"]] == [A, B])

print("-- capped flag")
client, row = run(answer(A, B), {"requirements": 2})
check("answer with as many requirements as the limit: capped", row["requirements_capped"] is True
      and row["schema_limits"] == {"requirements": 2})
client, row = run(answer(A), {"requirements": 2})
check("fewer requirements than the limit: not capped", row["requirements_capped"] is False)
client, row = run(answer(A, B))
check("no limits configured: never capped, schema_limits is None",
      row["requirements_capped"] is False and row["schema_limits"] is None)
client, row = run(answer(A, A), {"requirements": 2})
check("capped is judged before the repeats are removed (the model hit the limit)",
      row["requirements_capped"] is True and row["copy_total"] == 1)

print()
sys.exit(1 if check.failed else 0)
