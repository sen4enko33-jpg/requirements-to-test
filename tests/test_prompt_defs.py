"""Prompt v3 must carry the field definitions of the schema word for word (the local model never sees the schema text).

    python tests/test_prompt_defs.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.prompts import load_template  # noqa: E402
from src.schema import Extraction, Requirement  # noqa: E402

prompt = load_template("v3")
failed = 0
for model in (Extraction, Requirement):
    for name, field in model.model_fields.items():
        ok = field.description in prompt
        print(("ok   " if ok else "FAIL ") + f"{model.__name__}.{name}: description is in prompt v3")
        failed += not ok
sys.exit(1 if failed else 0)
