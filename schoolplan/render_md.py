"""Plain-text / Markdown digest -- handy for commit messages, mail or chat."""

from __future__ import annotations

import datetime as dt

from .highlights import CATEGORY_EMOJI, CATEGORY_LABELS
from .model import Plan


def _fmt(iso: str | None) -> str:
    if not iso:
        return "?"
    day = dt.date.fromisoformat(iso)
    names = ["man", "tir", "ons", "tor", "fre", "lør", "søn"]
    return f"{names[day.weekday()]} {day.day}.{day.month}."


def _short(iso: str | None) -> str:
    """Just the day and month -- the weekday name is already in the heading."""
    if not iso:
        return "?"
    day = dt.date.fromisoformat(iso)
    return f"{day.day}.{day.month}."


def render(plan: Plan, *, today: dt.date | None = None, horizon_days: int = 45) -> str:
    today = today or dt.date.today()
    iso_today = today.isoformat()
    horizon = (today + dt.timedelta(days=horizon_days)).isoformat()

    lines = [
        f"# Arbeidsplan {plan.school_class} – Gimle oppveksttun skole",
        "",
        f"Hentet: {plan.scraped_at}",
        f"Kilde: {plan.source_url}",
        "",
    ]

    current = next(
        (w for w in plan.weeks if w.monday and w.friday and w.monday <= iso_today <= w.friday),
        None,
    )
    if current:
        lines += [f"## Uke {current.week} ({_fmt(current.monday)} – {_fmt(current.friday)})", ""]
        if current.messages:
            lines.append("**Ukens viktige beskjeder**")
            lines += [f"- {m}" for m in current.messages]
            lines.append("")
        for day in current.days:
            lines.append(f"### {day.name} {_short(day.date)}")
            if not day.lessons:
                lines.append("_ingen timer ført opp_")
            for lesson in day.lessons:
                when = f"{lesson.start}–{lesson.end}" if lesson.start and lesson.end else (lesson.start or "")
                lines.append(f"- **{when} {lesson.subject}**"
                             + (f" — {lesson.detail}" if lesson.detail else ""))
                for item in lesson.homework:
                    lines.append(f"  - 📚 **Lekse:** {item}")
            lines.append("")

    upcoming = [h for h in plan.highlights if h.date and iso_today <= h.date <= horizon]
    lines += [f"## Fremover ({horizon_days} dager)", ""]
    if not upcoming:
        lines.append("_ingenting registrert_")
    for item in upcoming:
        emoji = CATEGORY_EMOJI.get(item.category, "📌")
        when = _fmt(item.date) + (f" {item.start}" if item.start else "")
        label = CATEGORY_LABELS.get(item.category, item.category)
        lines.append(f"- {emoji} `{when}` **{item.title}** _({label})_")
    lines.append("")
    return "\n".join(lines)


def summarise_changes(changes: dict) -> str:
    """One-line summary suitable for a commit subject."""
    if changes.get("first_run"):
        return "første kjøring"
    added, removed = len(changes.get("added", [])), len(changes.get("removed", []))
    if not added and not removed:
        return "ingen endringer"
    bits = []
    if added:
        bits.append(f"{added} nye")
    if removed:
        bits.append(f"{removed} fjernet")
    return ", ".join(bits)
