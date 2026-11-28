"""Checks of the long-term memory and the feedback (agent/memory.py) without network or models:
python tests/test_memory.py"""
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.limits import Limits
from agent.llm import ChatResult
from agent.loop import run_agent
from agent.memory import MAX_CHARS, MAX_FACTS, TTL_DAYS, Memory, handle_command, render_block
from agent.trace import Trace
from evals.run import load_tasks
from tools.echo import ECHO
from tools.registry import ToolRegistry

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.t


tmp = tempfile.TemporaryDirectory()
D, FB = Path(tmp.name) / "memory", Path(tmp.name) / "feedback.jsonl"
clock = Clock()


def mem(user="vit"):
    return Memory(user, D, FB, now=clock)


# --- writes and the rules of what stays
m = mem()
check("a new user: empty memory, nothing written yet", m.facts == [] and not (D / "vit.json").exists())
f1 = m.add("language: answer in English")
f2 = m.add("I work in the QA team of the remote work policy")
m.save()
check("saved to data/memory/<user>.json and read back", [f["text"] for f in mem().facts] == [f1["text"], f2["text"]])
check("a fact has id, source, creation and expiry dates", f1["id"] == 1 and f1["source"] == "remember"
      and f1["expires_at"].startswith(str((clock.t + timedelta(days=TTL_DAYS)).date())))
m.add("Language: answer in Ukrainian")
check("the same key replaces the old fact", [f["text"] for f in m.facts if f.get("key") == "language"] == ["Language: answer in Ukrainian"]
      and len(m.facts) == 2)
m.add("x" * 1000)
check(f"a long fact is cut to {MAX_CHARS} chars", len(m.facts[-1]["text"]) == MAX_CHARS)
for i in range(MAX_FACTS + 5):
    m.add(f"fact number {i}")
check(f"at most {MAX_FACTS} facts, the oldest go first", len(m.facts) == MAX_FACTS and m.facts[-1]["text"] == f"fact number {MAX_FACTS + 4}"
      and all("language" != f.get("key") for f in m.facts))
m.save()
clock.t += timedelta(days=TTL_DAYS + 1)
check(f"after {TTL_DAYS} days the facts expire on load", mem().facts == [])
clock.t = datetime(2026, 11, 1, tzinfo=timezone.utc)

m = mem("u2")
a, b = m.add("one fact"), m.add("another fact")
check("/forget n deletes one", m.forget(str(a["id"])) == 1 and [f["id"] for f in m.facts] == [b["id"]])
check("/forget all deletes all", m.forget("all") == 1 and m.facts == [])
for bad in ["../x", "a b", ""]:
    try:
        Memory(bad, D, FB)
        check(f"user name {bad!r} refused (it is a file name)", False)
    except ValueError:
        check(f"user name {bad!r} refused (it is a file name)", True)

# --- feedback
m = mem("u3")
try:
    m.feedback("good")
    check("feedback before any answer -> error", False)
except ValueError:
    check("feedback before any answer -> error", True)
m.remember_answer("Скільки днів на тиждень можна працювати віддалено?", "До двох днів.", "run-1")
m.feedback("bad", "too short")
m.feedback("fix", "also say how remote days are booked")
rows = [json.loads(l) for l in FB.read_text().splitlines()]
check("ratings and corrections go to feedback.jsonl with the question, answer and run id",
      [r["rating"] for r in rows] == ["bad", "fix"] and rows[1]["question"].startswith("Скільки") and rows[1]["run_id"] == "run-1"
      and rows[1]["correction"] == "also say how remote days are booked")
check("a /fix becomes a fact, a /bad does not", len(m.facts) == 1 and m.facts[0]["source"] == "fix"
      and "also say how remote days are booked" in m.facts[0]["text"] and "Скільки днів" in m.facts[0]["text"])

# --- commands
m = mem("u4")
check("a question is not a command", handle_command(m, "Скільки днів?") is None)
check("/remember", handle_command(m, "/remember answer briefly").startswith("Remembered (1)") and mem("u4").facts[0]["text"] == "answer briefly")
check("/memory lists the facts", "1. answer briefly" in handle_command(m, "/memory"))
check("/forget all", handle_command(m, "/forget all") == "Deleted 1 fact(s)." and mem("u4").facts == [])
check("/memory when empty", handle_command(m, "/memory") == "Memory is empty.")
for bad in ["/remember", "/fix", "/forget x", "/delete all"]:
    try:
        handle_command(m, bad)
        check(f"{bad!r} -> a clear error", False)
    except ValueError:
        check(f"{bad!r} -> a clear error", True)

# --- the prompt and the agent loop
check("no facts -> no memory block", render_block([]) == "" and mem("empty").prompt_block() == "")
block = render_block(["answer in English"])
check("the block lists the facts and keeps the rules above it", "- answer in English" in block and "does not replace the rules" in block)
check("only preferences: no corrections part", "Preferences" in block and "Corrections" not in block and "[" not in block)
fix_text = 'Correction of the answer to "Скільки днів?": also say how remote days are booked'
both = render_block(["answer in English", fix_text])
check("a /fix goes to the corrections part, which says the answer MUST cover it",
      both.index("- answer in English") < both.index("Corrections") < both.index("- " + fix_text) and "MUST also" in both)
check("only corrections: no preferences part", "Preferences" not in render_block([fix_text]))


class Recorder:
    name = "rec"

    def __init__(self):
        self.messages = None

    def chat(self, messages, tools, timeout_s=None):
        self.messages = messages
        return ChatResult("Two days.", tokens_in=10, tokens_out=2, cost_usd=0.0)


rec, tr = Recorder(), Trace()
run_agent("Скільки днів?", rec, ToolRegistry([ECHO]), Limits(), "SYSTEM", tr, memory=["answer in English"], memory_block=block)
check("run_agent: the memory block follows the system prompt", rec.messages[0]["content"] == "SYSTEM\n\n" + block)
check("run_agent: the facts used are in the trace", tr.of("start")[0]["memory"] == ["answer in English"])
rec2 = Recorder()
run_agent("q", rec2, ToolRegistry([ECHO]), Limits(), "SYSTEM", Trace())
check("run_agent without memory: the system prompt as it is", rec2.messages[0]["content"] == "SYSTEM")

# --- a correction of the same question is repeated next to it
from agent.memory import corrections_for, with_corrections  # noqa: E402

FIX = 'Correction of the answer to "Скільки днів на тиждень можна працювати віддалено?": також скажи, як бронювати дні'
check("corrections_for: the same question, case and punctuation ignored",
      corrections_for([FIX, "language: English"], "скільки днів на тиждень можна працювати віддалено") == ["також скажи, як бронювати дні"])
check("corrections_for: another question gets none", corrections_for([FIX], "Які core hours?") == [])
check("with_corrections: no fix -> the question as it is", with_corrections("Q?", ["language: English"]) == "Q?")
rec3, tr3 = Recorder(), Trace()
run_agent("Скільки днів на тиждень можна працювати віддалено?", rec3, ToolRegistry([ECHO]), Limits(), "S", tr3, memory=[FIX],
          memory_block=render_block([FIX]))
check("run_agent: the model gets the question with the user's correction next to it",
      rec3.messages[-1]["content"].endswith("(My earlier correction of your answer to this question: також скажи, як бронювати дні)"))
check("run_agent: the trace keeps the plain question and the message the model got",
      tr3.of("start")[0]["question"] == "Скільки днів на тиждень можна працювати віддалено?"
      and "My earlier correction" in tr3.of("start")[0]["user_message"])

# --- nothing but the user's commands can write the memory
import tools.build as build_mod  # noqa: E402

check("no tool of the agent can write the memory (it is not a tool)",
      "memory" not in Path(build_mod.__file__).read_text() and "agent.memory" not in Path(ROOT / "tools" / "registry.py").read_text())
mem_tasks = [t for t in load_tasks() if t["category"] == "memory"]
check("memory tasks: each starts with facts in setup.memory", mem_tasks and all(t["setup"]["memory"] for t in mem_tasks))

tmp.cleanup()
print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'all checks passed'}")
sys.exit(1 if FAILED else 0)
