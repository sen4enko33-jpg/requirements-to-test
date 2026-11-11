"""Fixed-size chunking: the baseline the structural strategy is compared with (windows of words, no structure)."""
from .blocks import Block


def chunk_fixed(blocks: list[Block], size: int = 300, overlap: float = 0.15) -> list[dict]:
    toks = [(w, ui, " > ".join(b.path)) for ui, b in enumerate(blocks) for w in b.text.split()]
    step = max(1, round(size * (1 - overlap)))
    out, i = [], 0
    while i < len(toks):
        win = toks[i:i + size]
        parts, prev = [], None
        for w, ui, _ in win:
            parts.append(("\n\n" if prev is not None and ui != prev else " ") + w if parts else w)
            prev = ui
        secs = list(dict.fromkeys(s for _, _, s in win))
        out.append({"text": "".join(parts), "n_words": len(win), "sections": secs})
        if i + size >= len(toks):
            break
        i += step
    return out
