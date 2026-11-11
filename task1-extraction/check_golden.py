import sys
from pathlib import Path

from pydantic import ValidationError

from src.schema import Extraction

GOLDEN_DIR = Path(__file__).parent / "data" / "golden"


def main():
    ids_path = GOLDEN_DIR / "golden_ids.txt"
    ids = [line.strip() for line in ids_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    ok = 0
    for text_id in ids:
        path = GOLDEN_DIR / f"{text_id}.json"
        if not path.exists():
            print(f"[MISSING] {text_id}")
            continue
        try:
            item = Extraction.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as e:
            print(f"[INVALID] {text_id}")
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                print(f"    {loc}: {err['msg']}")
            continue
        print(f"[OK] {text_id}: {len(item.requirements)} requirement(s)")
        ok += 1

    print(f"\n{ok}/{len(ids)} valid")
    sys.exit(0 if ok == len(ids) else 1)


if __name__ == "__main__":
    main()
