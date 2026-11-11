"""Checks of validation, the copy check and the single repair attempt, with a fake model client (no API calls).

    python tests/test_repair.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.clients.base import GenResult, ModelClient  # noqa: E402
from src.run import run_doc  # noqa: E402
from src.validate import check_copy, strip_running_headers  # noqa: E402

DOC_ID = sorted(p.stem for p in (ROOT / "data" / "noisy").glob("*.txt"))[0]
SOURCE = (ROOT / "data" / "noisy" / f"{DOC_ID}.txt").read_text(encoding="utf-8")


def real_statements(n):
    """n different 10-word runs of the real excerpt that the copy check accepts."""
    words, out, i = SOURCE.split(), [], 0
    while len(out) < n and i + 10 <= len(words):
        candidate = " ".join(words[i:i + 10])
        if not check_copy({"requirements": [{"text": candidate}]}, SOURCE):
            out.append(candidate)
            i += 40
        else:
            i += 1
    assert len(out) == n, "the test excerpt is too short"
    return out


def answer(*texts, type_="functional"):
    return json.dumps({
        "doc_title": None, "domain": "other", "language": "en", "actors": ["user"],
        "requirements": [{"id": None, "section": None, "text": t, "type": type_, "testable": "yes"} for t in texts],
        "has_acceptance_criteria": False, "open_questions": [],
    })


GOOD1, GOOD2 = real_statements(2)
PARAPHRASE = "The operator is able to carry out an entirely different action whenever it wishes"
VALID = answer(GOOD1, GOOD2)
BAD_SCHEMA = answer(GOOD1, GOOD2, type_="banana")          # valid JSON, wrong enum value
BAD_JSON = '{"doc_title": null, "domain": '                # cut in the middle
ONE_PARAPHRASE = answer(GOOD1, PARAPHRASE)                 # 1 of 2 requirements is not in the excerpt
TWO_PARAPHRASES = answer(PARAPHRASE, PARAPHRASE + " twice")


class FakeClient(ModelClient):
    """Returns the prepared answers one by one and remembers the prompts it got."""
    name = "fake-model"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def generate(self, prompt, response_model, sampling):
        self.prompts.append(prompt)
        text, error = self.answers.pop(0)
        return GenResult(text, 1.0, 100, 50, 1, error, 0.001)


def run(*answers):
    client = FakeClient(*answers)
    row = run_doc(client, DOC_ID, "fake", "v1", "A", {"temperature": 0.0, "top_p": 1.0})
    return client, row


def check(name, condition):
    print(("ok   " if condition else "FAIL ") + name)
    if not condition:
        check.failed += 1
check.failed = 0


print("-- valid answer")
client, row = run((VALID, None))
check("valid and copied: 1 call, status ok, no repair, 0 copy violations",
      len(client.prompts) == 1 and row["status"] == "ok" and not row["repair_attempted"]
      and row["copy_violations"] == 0 and row["copy_total"] == 2 and row["error"] is None)

print("-- schema errors")
client, row = run((BAD_SCHEMA, None), (VALID, None))
check("bad schema + good repair: 2 calls, ok, repaired (reason schema)", len(client.prompts) == 2
      and row["status"] == "ok" and row["repaired"] and row["repair_reason"] == "schema" and row["error"] is None)
check("repair prompt contains the bad answer and the schema errors",
      "banana" in client.prompts[1] and "Validation errors" in client.prompts[1]
      and "requirements.0.type" in client.prompts[1])
check("tokens, latency and cost are totals of both calls",
      row["tokens_in"] == 200 and row["tokens_out"] == 100 and row["latency_s"] == 2.0
      and row["attempts"] == 2 and abs(row["cost_usd"] - 0.002) < 1e-9)
check("first schema errors are logged", row["validation_errors"] and "requirements.0.type" in row["validation_errors"])
client, row = run((BAD_JSON, None), (VALID, None))
check("broken JSON + good repair: ok, repaired", row["status"] == "ok" and row["repaired"])
client, row = run((BAD_SCHEMA, None), (BAD_SCHEMA, None))
check("schema bad + bad: exactly 2 calls, failed", len(client.prompts) == 2 and row["status"] == "failed"
      and row["repair_attempted"] and not row["repaired"] and row["extraction"] is None
      and row["error"].startswith("schema validation failed after repair"))
client, row = run((BAD_SCHEMA, None), (None, "APITimeoutError: timeout"))
check("repair call fails after a schema error: failed, reason kept",
      row["status"] == "failed" and "repair failed: APITimeoutError" in row["error"])
client, row = run((None, "truncated: max_tokens reached"))
check("truncated answer: 1 call, no repair, failed",
      len(client.prompts) == 1 and row["status"] == "failed" and not row["repair_attempted"]
      and row["error"] == "truncated: max_tokens reached")

print("-- copy check")
client, row = run((ONE_PARAPHRASE, None), (VALID, None))
check("paraphrase + good repair: 2 calls, ok, repaired (reason copy)", len(client.prompts) == 2
      and row["status"] == "ok" and row["repaired"] and row["repair_reason"] == "copy"
      and row["copy_violations"] == 0)
check("repair prompt names the not copied requirement",
      "not copied from the excerpt" in client.prompts[1] and "requirements.1.text" in client.prompts[1])
check("first answer's violations are logged", row["copy_errors_first"] and len(row["copy_errors_first"]) == 1
      and row["copy_first_total"] == 2)
client, row = run((ONE_PARAPHRASE, None), (ONE_PARAPHRASE, None))
check("paraphrase stays: 2 calls, status partial_failed, 1 violation of 2",
      len(client.prompts) == 2 and row["status"] == "partial_failed" and row["copy_violations"] == 1
      and row["copy_total"] == 2 and row["extraction"] is not None
      and row["error"].startswith("copy check failed after repair: 1 of 2"))
client, row = run((ONE_PARAPHRASE, None), (TWO_PARAPHRASES, None))
check("worse repair (2 violations instead of 1) is not accepted: first answer kept",
      row["status"] == "partial_failed" and row["copy_violations"] == 1 and not row["repaired"]
      and [r["text"] for r in row["extraction"]["requirements"]] == [GOOD1, PARAPHRASE])
GOOD2_TWICE_BAD = answer(GOOD1, GOOD2, PARAPHRASE)           # 2 correct requirements and 1 not copied
client, row = run((GOOD2_TWICE_BAD, None), (answer(GOOD1), None))
check("repair that drops a good requirement to remove the bad one is rejected (2 correct -> 1)",
      row["status"] == "partial_failed" and row["copy_violations"] == 1 and not row["repaired"]
      and row["copy_total"] == 3)
client, row = run((GOOD2_TWICE_BAD, None), (answer(), None))
check("repair that returns an empty list is rejected", row["status"] == "partial_failed"
      and not row["repaired"] and row["copy_total"] == 3)
client, row = run((GOOD2_TWICE_BAD, None), (answer(GOOD1, GOOD2), None))
check("repair that removes only the bad requirement is accepted (2 correct -> 2)",
      row["status"] == "ok" and row["repaired"] and row["copy_violations"] == 0 and row["copy_total"] == 2)
client, row = run((ONE_PARAPHRASE, None), (BAD_SCHEMA, None))
check("repair that breaks the schema is not accepted: first answer kept",
      row["status"] == "partial_failed" and row["copy_violations"] == 1 and not row["repaired"])
client, row = run((ONE_PARAPHRASE, None), (None, "APITimeoutError: timeout"))
check("repair call fails after a copy error: partial_failed, reason kept",
      row["status"] == "partial_failed" and "repair failed: APITimeoutError" in row["error"])

print("-- what the copy check must accept")
layout = [f"• 1. {GOOD1.upper()}", GOOD2.replace(" ", "\n", 3), f"(a) {GOOD1}"]
check("bullets, list numbers, case and line breaks are not violations",
      check_copy({"requirements": [{"text": t} for t in layout]}, SOURCE) == [])
client, row = run((answer(*layout), None))
check("such an answer is not repaired", len(client.prompts) == 1 and row["status"] == "ok")
check("a word replaced by another one is a violation",
      len(check_copy({"requirements": [{"text": GOOD1.replace(GOOD1.split()[4], "zebra")}]}, SOURCE)) == 1)
check("two pieces taken from far apart places are a violation",
      len(check_copy({"requirements": [{"text": GOOD1 + " " + GOOD2}]}, SOURCE)) == 1)

print("-- page headers")
two_pieces = f"{GOOD1}\n\nPage 7\n\nSoftware Requirements Specification\n\n•\n\nPage 8\n\nSoftware Requirements Specification\n\n" \
             f"{GOOD2}\n\nPage 9\n\nSoftware Requirements Specification\n"
joined = {"requirements": [{"text": f"{GOOD1} {GOOD2}"}]}
check("a statement split by page headers is accepted when the model dropped them",
      check_copy(joined, two_pieces) == [])
check("the same statement with unrelated text in between is still a violation",
      len(check_copy(joined, f"{GOOD1} " + " ".join(f"filler{i}" for i in range(40)) + f" {GOOD2}")) == 1)
check("page numbers and lone bullets are removed, ordinary lines are kept",
      strip_running_headers("Page 1\n•\n12\nA real sentence here.\n") == "A real sentence here.")
check("a line repeated 3+ times is a running header and is removed; twice is kept",
      "Header X" not in strip_running_headers("Header X\na\nHeader X\nb\nHeader X\n")
      and "Twice" in strip_running_headers("Twice\na\nTwice\n"))

print("-- run log")
check("row logs model, prompt version and sampling",
      row["model"] == "fake-model" and row["prompt_version"] == "v1"
      and row["sampling"] == {"temperature": 0.0, "top_p": 1.0} and row["sampling_name"] == "A")

sys.exit(1 if check.failed else 0)
