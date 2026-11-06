"""Versioned RAG prompts: rag/prompts/answer_<version>.md with the placeholders <<CONTEXT>> and <<QUESTION>>."""
import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
PLACEHOLDERS = ("CONTEXT", "QUESTION")


def load_template(version: str) -> str:
    path = PROMPTS_DIR / f"answer_{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt version '{version}' not found: {path}")
    template = path.read_text(encoding="utf-8")
    for name in PLACEHOLDERS:
        if template.count(f"<<{name}>>") != 1:
            raise ValueError(f"{path.name} must contain <<{name}>> exactly once")
    return template


def build_prompt(version: str, context: str, question: str) -> str:
    """One pass over the template: text that looks like a placeholder inside the context or the question stays as it is."""
    values = {"CONTEXT": context.strip(), "QUESTION": question.strip()}
    return re.sub(r"<<(CONTEXT|QUESTION)>>", lambda m: values[m.group(1)], load_template(version))
