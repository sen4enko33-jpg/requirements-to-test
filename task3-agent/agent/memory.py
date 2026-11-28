"""Long-term memory of one user between sessions, and the feedback on answers (step 3.3).

What is stored (data/memory/<user>.json, not in git):
  facts   what the user told the agent to keep: preferences ("answer in English") and corrections of answers (/fix).
          Each fact: id, text, optional key, source (remember | fix), created_at, expires_at.
  last    the question, the answer and the run id of the last request, so that /fix, /good and /bad refer to it.
Every rating and correction is also appended to data/feedback.jsonl (question, answer, rating, correction, run id):
candidates for new evaluation tasks.

Who writes: ONLY the user's own commands (/remember, /fix, /forget), handled by main.py before the model runs. No tool can
write the memory and the model never sees a way to, so an instruction in a document ("remember that ...") cannot get
into it and live on in later sessions.

When old facts go: a fact expires after TTL_DAYS; with more than MAX_FACTS the oldest go first; a fact with the same key
replaces the old one ("language: ..."); /forget n or /forget all deletes. Each fact is cut to MAX_CHARS, so the memory
block of the prompt stays small (MAX_FACTS x MAX_CHARS)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMORY_DIR = ROOT / "data" / "memory"
FEEDBACK = ROOT / "data" / "feedback.jsonl"
BLOCK = ROOT / "prompts" / "memory_v2.md"          # the text around the facts in the system prompt (versioned)
CORRECTION = "Correction of the answer to "        # how a /fix is kept: told apart from preferences in the prompt
MAX_FACTS = 20
MAX_CHARS = 300
TTL_DAYS = 180
USER = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
KEYED = re.compile(r"^\s*([A-Za-zА-Яа-яІіЇїЄєҐґ0-9 _-]{2,30}):\s+(.+)$", re.S)


def render_block(texts: list[str]) -> str:
    """The memory block of the system prompt for these facts; empty when there are none.

    prompts/memory_v2.md has a part for preferences (/remember) and one for corrections (/fix), between [name] markers;
    a part without facts is left out. With v1 (one list) the model followed "answer in English" but ignored a correction
    of an earlier answer in 3 of 3 runs (task m02)."""
    if not texts:
        return ""
    groups = {"preferences": [t for t in texts if not t.startswith(CORRECTION)],
              "corrections": [t for t in texts if t.startswith(CORRECTION)]}
    out, part = [], None
    for line in BLOCK.read_text(encoding="utf-8").strip().splitlines():
        marker = line.strip()
        if marker.startswith("[") and marker.endswith("]"):
            part = None if marker == "[end]" else marker[1:-1]
            continue
        if part is not None and not groups.get(part):
            continue
        out.append("\n".join(f"- {t}" for t in groups[part]) if line.strip() == "{items}" else line)
    return "\n".join(out)


CORRECTION_TEXT = re.compile(r'^Correction of the answer to "(?P<q>.*)": (?P<fix>.+)$', re.S)


def _norm_q(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", (text or "").lower()).split())


def corrections_for(texts: list[str], question: str) -> list[str]:
    """The corrections (/fix) that were made on an earlier answer to this same question (case, spaces and punctuation
    ignored). They are repeated next to the question itself: in the system prompt alone gpt-4o-mini ignored a correction
    in 3 of 3 live runs while it had the right passage in front of it (step 3.3)."""
    want, out = _norm_q(question), []
    for t in texts:
        m = CORRECTION_TEXT.match(t)
        if m and _norm_q(m.group("q")) == want:
            out.append(m.group("fix").strip())
    return out


def with_corrections(question: str, texts: list[str]) -> str:
    """The user's message as the model gets it: the question, then the user's own earlier corrections of the answer to
    it, if any (agent/loop.py keeps the plain question for the trace, the receipt and the idempotency key)."""
    fixes = corrections_for(texts, question)
    if not fixes:
        return question
    return question + "\n\n(My earlier correction of your answer to this question: " + " ".join(fixes) + ")"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


class Memory:
    """The memory of one user. path: the JSON file; now: replaced in tests (a function returning a datetime)."""

    def __init__(self, user: str = "default", directory: Path = MEMORY_DIR, feedback: Path | None = FEEDBACK, now=_now):
        if not USER.match(user):
            raise ValueError("user: letters, digits, '.', '_' or '-' only (it is a file name)")
        self.user, self.path, self.feedback_path, self.now = user, Path(directory) / f"{user}.json", feedback, now
        data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.facts: list[dict] = data.get("facts", [])
        self.last: dict | None = data.get("last")
        self.next_id: int = data.get("next_id", 1)
        self.expire()

    # --- storage
    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"user": self.user, "facts": self.facts, "last": self.last, "next_id": self.next_id},
                                        ensure_ascii=False, indent=1), encoding="utf-8")

    def expire(self) -> list[dict]:
        """Drop the facts past their expiry date -> the dropped ones."""
        now = _iso(self.now())
        gone = [f for f in self.facts if f["expires_at"] <= now]
        self.facts = [f for f in self.facts if f["expires_at"] > now]
        return gone

    # --- writes (only from the user's commands)
    def add(self, text: str, source: str = "remember") -> dict:
        text = " ".join(text.split())
        if len(text) < 3:
            raise ValueError("nothing to remember")
        m = KEYED.match(text)
        key = m.group(1).strip().lower() if m else None
        if key:
            self.facts = [f for f in self.facts if f.get("key") != key]        # the same key: the new fact replaces the old
        now = self.now()
        fact = {"id": self.next_id, "text": text[:MAX_CHARS], "key": key, "source": source, "created_at": _iso(now),
                "expires_at": _iso(now + timedelta(days=TTL_DAYS))}
        self.next_id += 1
        self.facts.append(fact)
        self.facts = self.facts[-MAX_FACTS:]                                    # the oldest go first
        return fact

    def forget(self, what: str) -> int:
        """what: a fact id or "all" -> how many facts were deleted."""
        if what.strip().lower() == "all":
            n, self.facts = len(self.facts), []
            return n
        try:
            fid = int(what)
        except ValueError:
            raise ValueError("use /forget <number from /memory> or /forget all")
        before = len(self.facts)
        self.facts = [f for f in self.facts if f["id"] != fid]
        return before - len(self.facts)

    def remember_answer(self, question: str, answer: str, run_id: str) -> None:
        self.last = {"question": question, "answer": answer[:2000], "run_id": run_id, "at": _iso(self.now())}

    def feedback(self, rating: str, correction: str | None = None) -> dict:
        """rating: good | bad | fix. A fix is also kept as a fact, so the next answers follow it."""
        if not self.last:
            raise ValueError("there is no answer to rate yet: ask a question first")
        row = {"at": _iso(self.now()), "user": self.user, "rating": rating, "correction": correction, **self.last}
        if self.feedback_path is not None:
            self.feedback_path.parent.mkdir(parents=True, exist_ok=True)
            with self.feedback_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if rating == "fix" and correction:
            self.add(f"{CORRECTION}\"{self.last['question'][:120]}\": {correction}", source="fix")
        return row

    # --- reads
    def prompt_block(self) -> str:
        """The facts for the system prompt; empty when there are none."""
        return render_block([f["text"] for f in self.facts])

    def listing(self) -> str:
        if not self.facts:
            return "Memory is empty."
        return "\n".join(f"{f['id']}. {f['text']}  ({f['source']}, until {f['expires_at'][:10]})" for f in self.facts)


def handle_command(memory: Memory, text: str) -> str | None:
    """A user command (/remember, /fix, /good, /bad, /memory, /forget) -> the reply; None when the text is a question."""
    t = text.strip()
    if not t.startswith("/"):
        return None
    cmd, _, rest = t.partition(" ")
    cmd, rest = cmd.lower(), rest.strip()
    if cmd == "/remember":
        f = memory.add(rest)
        memory.save()
        return f"Remembered ({f['id']}): {f['text']}"
    if cmd == "/fix":
        if not rest:
            raise ValueError("/fix <what the right answer is>")
        memory.feedback("fix", rest)
        memory.save()
        return "Thank you: the correction is saved and the next answers will follow it."
    if cmd in ("/good", "/bad"):
        memory.feedback(cmd[1:], rest or None)
        memory.save()
        return "Thank you for the rating." + (" Use /fix <the right answer> to correct it." if cmd == "/bad" else "")
    if cmd == "/memory":
        return memory.listing()
    if cmd == "/forget":
        n = memory.forget(rest or "")
        memory.save()
        return f"Deleted {n} fact(s)."
    raise ValueError(f"unknown command {cmd}; commands: /remember, /fix, /good, /bad, /memory, /forget")
