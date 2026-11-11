import csv
import random
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent
IN_DIR = BASE_DIR / "data" / "texts"
OUT_DIR = BASE_DIR / "data" / "noisy"
LOG_PATH = BASE_DIR / "data" / "noise_log.csv"

SEED = 7
N_UKRAINIAN = 7     # texts that get Ukrainian sentences (language: mixed)
N_TYPOS = 10        # texts that get typos (~1/3 of 31)
N_DROPPED = 8       # texts that lose 1-2 sentences
TYPO_RATE = 0.02    # share of eligible words corrupted inside a selected text
MIN_WORDS_TO_DROP = 8

UK_PHRASES = [
    "Система повинна дозволяти користувачу входити за допомогою електронної пошти та пароля.",
    "Час відгуку системи не має перевищувати дві секунди.",
    "Якщо введені дані некоректні, користувач бачить повідомлення про помилку.",
    "Адміністратор може змінювати налаштування системи та керувати ролями користувачів.",
    "Усі дані мають зберігатися щонайменше п'ять років.",
    "Система повинна підтримувати експорт звіту у форматі PDF.",
    "Доступ до особистих даних мають лише авторизовані користувачі.",
    "Після трьох невдалих спроб входу обліковий запис блокується на 15 хвилин.",
]


def to_units(text):
    """Split into [sentence, separator] pairs so paragraph breaks survive."""
    parts = re.split(r"(?<=[.!?])(\s+)", text)
    return [[parts[i], parts[i + 1] if i + 1 < len(parts) else ""] for i in range(0, len(parts), 2)]


def from_units(units):
    return "".join(s + sep for s, sep in units)


def drop_sentences(units):
    candidates = [i for i, (s, _) in enumerate(units) if len(s.split()) >= MIN_WORDS_TO_DROP]
    k = min(random.randint(1, 2), len(candidates))
    for i in sorted(random.sample(candidates, k), reverse=True):
        units.pop(i)
    return k


def corrupt_word(w):
    i = random.randrange(1, len(w) - 1)
    op = random.choice(["swap", "drop", "dup"])
    if op == "swap":
        return w[:i] + w[i + 1] + w[i] + w[i + 2:]
    if op == "drop":
        return w[:i] + w[i + 1:]
    return w[:i] + w[i] + w[i:]


def add_typos(text):
    count = 0

    def repl(m):
        nonlocal count
        w = m.group(0)
        if random.random() < TYPO_RATE:
            count += 1
            return corrupt_word(w)
        return w

    return re.sub(r"[A-Za-z]{5,}", repl, text), count


def insert_ukrainian(units):
    phrases = random.sample(UK_PHRASES, random.randint(1, 2))
    for phrase in phrases:
        pos = random.randrange(len(units))
        units.insert(pos + 1, [phrase, " "])
    return phrases


def main():
    random.seed(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(IN_DIR.glob("*.txt"))
    names = [f.stem for f in files]

    uk_set = set(random.sample(names, N_UKRAINIAN))
    typo_set = set(random.sample(names, N_TYPOS))
    drop_set = set(random.sample(names, N_DROPPED))

    rows = []
    for f in files:
        text_id = f.stem
        units = to_units(f.read_text(encoding="utf-8"))

        dropped = drop_sentences(units) if text_id in drop_set else 0
        text = from_units(units)

        typos = 0
        if text_id in typo_set:
            text, typos = add_typos(text)

        phrases = []
        if text_id in uk_set:
            units = to_units(text)
            phrases = insert_ukrainian(units)
            text = from_units(units)

        (OUT_DIR / f.name).write_text(text, encoding="utf-8")
        rows.append([text_id, typos, dropped, len(phrases), " | ".join(phrases)])

    with LOG_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["text_id", "typos", "dropped_sentences", "uk_phrases", "uk_text"])
        writer.writerows(rows)

    print(f"Done: {len(rows)} noisy texts -> {OUT_DIR}")


if __name__ == "__main__":
    main()
