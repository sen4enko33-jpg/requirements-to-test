from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
PLACEHOLDER = "<<DOCUMENT>>"


def load_template(version: str) -> str:
    """Read prompts/extract_<version>.md and check it has exactly one placeholder."""
    path = PROMPTS_DIR / f"extract_{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt version '{version}' not found: {path}")
    template = path.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise ValueError(f"{path.name} must contain {PLACEHOLDER} exactly once")
    return template


def build_prompt(version: str, document: str) -> str:
    """Insert the document text into the prompt template of the given version."""
    return load_template(version).replace(PLACEHOLDER, document.strip(), 1)
