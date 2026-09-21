"""Classify Norwegian plan text into the things a parent actually needs to see.

Everything here is keyword driven and deliberately conservative: an ordinary
lesson ("Matematikk. Tema: negative tall") produces no highlight, while a test,
a trip, a day off, a meeting or a "husk lader" note does.
"""

from __future__ import annotations

import re

HOMEWORK_PREFIX = re.compile(r"^\s*(lekse[rn]?|hjemmelekse|til\s+neste\s+time)\s*[:\-–]\s*", re.I)

# Order matters: the first category that matches wins.
CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "dayoff",
        (
            "planleggingsdag", "fridag", "fri dag", "høstferie", "hostferie", "vinterferie",
            "juleferie", "påskeferie", "paskeferie", "sommerferie", "ferie", "helligdag",
            "fridager", "skolefri", "elevfri", "julaften", "lille julaften", "juledag",
            "nyttårsaften", "1. mai", "17. mai", "kristi himmelfart", "pinse", "skjærtorsdag",
            "langfredag", "påskeaften",
        ),
    ),
    (
        "test",
        (
            "nasjonal prøve", "nasjonale prøver", "prøve", "prøver", "tentamen", "eksamen",
            "kartlegging", "kartleggingsprøve", "innlevering", "leveres", "frist",
            "presentasjon", "presentere", "framføring", "fremføring", "muntlig vurdering",
            "vurderingssituasjon", "heldagsprøve", "test",
        ),
    ),
    (
        "trip",
        (
            "ekskursjon", "leirskole", "skoletur", "klassetur", "utflukt", "tur til",
            "på tur", "busstur", "skitur", "aktivitetsdag", "turdag", "bli-kjent-tur",
            "museum", "besøk til", "vi drar", "vi reiser", "idrettsdag", "friluftsdag",
        ),
    ),
    (
        "meeting",
        (
            "foreldremøte", "utviklingssamtale", "konferansetime", "foreldresamtale",
            "elevsamtale", "møte", "fau", "skolefotografering", "fotografering",
            "mot-økt", "mot-okt", "samling", "informasjonsmøte", "kontaktmøte",
        ),
    ),
    (
        "bring",
        (
            "husk", "ta med", "du trenger", "medbring", "ha med", "husk lader",
            "kle deg", "gymtøy", "gymtoy", "matpakke",
        ),
    ),
]

CATEGORY_LABELS = {
    "homework": "Lekser",
    "dayoff": "Fri / ikke skole",
    "test": "Prøve / innlevering",
    "trip": "Tur / ekskursjon",
    "meeting": "Møte / arrangement",
    "bring": "Husk å ta med",
    "notice": "Beskjed",
}

CATEGORY_EMOJI = {
    "homework": "📚",
    "dayoff": "🏖️",
    "test": "📝",
    "trip": "🚌",
    "meeting": "👥",
    "bring": "🎒",
    "notice": "📌",
}

# Categories that describe something genuinely outside the normal weekly rhythm.
OUT_OF_ORDINARY = ("homework", "dayoff", "test", "trip", "meeting", "bring", "notice")


def classify(text: str) -> list[str]:
    """Return every category whose keywords appear in ``text``."""
    lowered = (text or "").lower()
    if not lowered.strip():
        return []
    tags = [cat for cat, words in CATEGORY_KEYWORDS if any(w in lowered for w in words)]
    return tags


def primary_category(text: str, default: str = "notice") -> str:
    tags = classify(text)
    return tags[0] if tags else default


def split_homework(lines: list[str]) -> tuple[list[str], list[str]]:
    """Separate "Lekse: ..." lines from the rest of a lesson cell.

    A homework line may wrap onto following lines, so once we are inside one we
    keep appending until a line looks like the start of new prose.
    """
    homework: list[str] = []
    detail: list[str] = []
    in_homework = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            in_homework = False
            continue
        match = HOMEWORK_PREFIX.match(stripped)
        if match:
            homework.append(stripped[match.end():].strip() or stripped)
            in_homework = True
        elif in_homework and not _starts_new_thought(stripped):
            homework[-1] = f"{homework[-1]} {stripped}".strip()
        else:
            in_homework = False
            detail.append(stripped)
    return [h for h in homework if h], detail


def _starts_new_thought(line: str) -> bool:
    """Heuristic: a continuation line is lowercase-ish and does not open a sentence."""
    return bool(re.match(r"^(vi|i timen|du skal|dere)\b", line, re.I))
