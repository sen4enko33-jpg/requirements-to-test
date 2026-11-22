"""Descriptions of the tools live in prompts/tools/<name>.yaml (versioned like prompts, changes in prompts/CHANGELOG.md),
not in the code. The argument schemas stay in the code (Pydantic), because the code validates them."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

DIR = Path(__file__).resolve().parents[1] / "prompts" / "tools"


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    """{"name", "version", "description"} of a tool."""
    data = yaml.safe_load((DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    if data.get("name") != name or not data.get("version") or not data.get("description"):
        raise ValueError(f"prompts/tools/{name}.yaml needs name: {name}, version and description")
    return data


def description(name: str) -> str:
    return load(name)["description"].strip()


def version(name: str) -> str:
    return load(name)["version"]
