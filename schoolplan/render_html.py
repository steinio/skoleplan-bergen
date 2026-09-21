"""Render the plan as one self-contained, mobile-friendly HTML dashboard."""

from __future__ import annotations

import datetime as dt
import html

from .highlights import CATEGORY_EMOJI, CATEGORY_LABELS
from .model import Highlight, Plan

_CSS = """
:root{
  --bg:#f6f7f9; --card:#fff; --ink:#15181d; --muted:#5d6672; --line:#e3e7ec;
  --accent:#1f6feb; --chip:#eef2f7;
  --homework:#b8860b; --dayoff:#0d8a5f; --test:#c0392b;
  --trip:#7d3cc6; --meeting:#1f6feb; --bring:#a05a00; --notice:#5d6672;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#0f1115; --card:#171a21; --ink:#e8eaed; --muted:#9aa4b2; --line:#272c36;
    --accent:#5a9cff; --chip:#222735;
    --homework:#e2b44a; --dayoff:#45c99a; --test:#ff7b6b;
    --trip:#b98cf0; --meeting:#5a9cff; --bring:#e0a45c; --notice:#9aa4b2;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-text-size-adjust:100%}
.wrap{max-width:860px;margin:0 auto;padding:16px}
header{padding:8px 0 4px}
h1{font-size:1.5rem;margin:0 0 4px}
h2{font-size:1.1rem;margin:28px 0 10px;letter-spacing:.01em}
h3{font-size:.95rem;margin:0 0 8px}
.sub{color:var(--muted);font-size:.85rem;margin:0}
.sub a{color:var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:14px 16px;margin-bottom:12px}
.day{border-left:3px solid var(--line);padding-left:12px;margin:14px 0}
.day.today{border-left-color:var(--accent)}
.dayhead{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;margin-bottom:6px}
.dayhead b{font-size:1rem}
.lesson{padding:7px 0;border-top:1px dashed var(--line)}
.lesson:first-of-type{border-top:0}
.time{color:var(--muted);font-size:.78rem;font-variant-numeric:tabular-nums}
.subject{font-weight:600}
.detail{color:var(--muted);font-size:.88rem;margin-top:2px}
.hw{margin-top:5px;padding:7px 10px;border-radius:8px;background:var(--chip);
  border-left:3px solid var(--homework);font-size:.9rem}
.hw b{color:var(--homework)}
ul.msg{margin:6px 0 0;padding-left:20px}
ul.msg li{margin:3px 0}
.item{display:flex;gap:10px;padding:9px 0;border-top:1px solid var(--line);align-items:flex-start}
.item:first-of-type{border-top:0}
.ic{font-size:1.05rem;line-height:1.35;flex:none}
.when{color:var(--muted);font-size:.78rem;font-variant-numeric:tabular-nums}
.tag{display:inline-block;font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;
  padding:1px 7px;border-radius:99px;background:var(--chip);color:var(--muted);
  vertical-align:middle;margin-left:6px}
.empty{color:var(--muted);font-style:italic}
.chg-add{color:var(--dayoff)} .chg-del{color:var(--test)}
footer{color:var(--muted);font-size:.78rem;margin:32px 0 12px;text-align:center}
footer a{color:var(--accent)}
"""


def _e(text: str) -> str:
    return html.escape(text or "", quote=True)


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    day = dt.date.fromisoformat(iso)
    names = ["man", "tir", "ons", "tor", "fre", "lør", "søn"]
    return f"{names[day.weekday()]} {day.day}.{day.month}."


def render(plan: Plan, *, today: dt.date | None = None,
           changes: dict | None = None, ics_url: str = "") -> str:
    today = today or dt.date.today()
    iso_today = today.isoformat()

    current = next(
        (w for w in plan.weeks if w.monday and w.friday and w.monday <= iso_today <= w.friday),
        None,
    ) or next((w for w in plan.weeks if w.monday and w.monday >= iso_today), None)

    upcoming = [
        h for h in plan.highlights
        if h.date and iso_today <= h.date <= (today + dt.timedelta(days=45)).isoformat()
    ]
    later = [h for h in plan.highlights
             if h.date and h.date > (today + dt.timedelta(days=45)).isoformat()]

    parts = [
        "<!doctype html><html lang=\"no\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
        f"<title>Arbeidsplan {_e(plan.school_class)}</title>",
        f"<style>{_CSS}</style></head><body><div class=\"wrap\">",
        "<header>",
        f"<h1>Arbeidsplan {_e(plan.school_class)}</h1>",
        f"<p class=\"sub\">Gimle oppveksttun skole &middot; oppdatert "
        f"{_e(plan.scraped_at[:16].replace('T', ' '))} UTC &middot; "
        f"<a href=\"{_e(plan.source_url)}\">original</a>"
        + (f" &middot; <a href=\"{_e(ics_url)}\">kalender</a>" if ics_url else "")
        + "</p></header>",
    ]

    if changes and changes.get("added") or changes and changes.get("removed"):
        parts.append(_changes_card(changes))

    parts.append("<h2>Denne uken</h2>")
    parts.append(_week_card(current, today) if current
                 else "<div class=\"card empty\">Ingen ukeplan funnet.</div>")

    parts.append("<h2>Fremover (6 uker)</h2>")
    parts.append(_items_card(upcoming, today, "Ingenting registrert."))

    if later:
        parts.append("<h2>Senere i terminen</h2>")
        parts.append(_items_card(later, today, ""))

    parts.append(
        "<footer>Hentet automatisk fra skolens publiserte arbeidsplan. "
        f"<a href=\"{_e(plan.index_url)}\">bergen.kommune.no</a></footer>"
    )
    parts.append("</div></body></html>")
    return "\n".join(parts)


def _week_card(week, today: dt.date) -> str:
    out = [f"<div class=\"card\"><h3>Uke {week.week} &middot; "
           f"{_fmt_date(week.monday)} – {_fmt_date(week.friday)}</h3>"]

    if week.messages:
        out.append("<div><b>Ukens viktige beskjeder</b><ul class=\"msg\">")
        out.extend(f"<li>{_e(m)}</li>" for m in week.messages)
        out.append("</ul></div>")

    for day in week.days:
        is_today = day.date == today.isoformat()
        out.append(f"<div class=\"day{' today' if is_today else ''}\">")
        span = f"{day.starts}–{day.ends}" if day.starts and day.ends else ""
        out.append(
            f"<div class=\"dayhead\"><b>{_e(day.name)}</b>"
            f"<span class=\"when\">{_fmt_date(day.date)}{'  ' + span if span else ''}</span>"
            + ("<span class=\"tag\">i dag</span>" if is_today else "")
            + "</div>"
        )
        if not day.lessons:
            out.append("<div class=\"empty\">Ingen timer ført opp.</div>")
        for lesson in day.lessons:
            out.append("<div class=\"lesson\">")
            when = f"{lesson.start}–{lesson.end}" if lesson.start and lesson.end else (lesson.start or "")
            out.append(f"<div class=\"time\">{_e(when)}</div>")
            tags = "".join(
                f"<span class=\"tag\">{_e(CATEGORY_LABELS.get(t, t))}</span>"
                for t in lesson.tags if t != "homework"
            )
            out.append(f"<div class=\"subject\">{_e(lesson.subject)}{tags}</div>")
            if lesson.detail:
                out.append(f"<div class=\"detail\">{_e(lesson.detail)}</div>")
            for item in lesson.homework:
                out.append(f"<div class=\"hw\"><b>Lekse:</b> {_e(item)}</div>")
            out.append("</div>")
        out.append("</div>")

    if week.teachers:
        out.append(f"<p class=\"sub\">Kontaktlærere: {_e(week.teachers)}</p>")
    out.append("</div>")
    return "".join(out)


def _items_card(items: list[Highlight], today: dt.date, empty: str) -> str:
    if not items:
        return f"<div class=\"card empty\">{_e(empty)}</div>" if empty else ""
    out = ["<div class=\"card\">"]
    for item in items:
        emoji = CATEGORY_EMOJI.get(item.category, "📌")
        when = _fmt_date(item.date)
        if item.start:
            when += f" {item.start}"
        if item.all_week:
            when += " (hele uken)"
        colour = f"color:var(--{item.category})" if item.category in CATEGORY_EMOJI else ""
        out.append(
            f"<div class=\"item\"><span class=\"ic\">{emoji}</span><div>"
            f"<div><span style=\"{colour}\">{_e(item.title)}</span>"
            f"<span class=\"tag\">{_e(CATEGORY_LABELS.get(item.category, item.category))}</span></div>"
            f"<div class=\"when\">{_e(when)} &middot; uke {item.week}</div>"
            + (f"<div class=\"detail\">{_e(item.detail)}</div>" if item.detail
               and not item.detail.startswith("Oversiktsplan") else "")
            + "</div></div>"
        )
    out.append("</div>")
    return "".join(out)


def _changes_card(changes: dict) -> str:
    out = ["<div class=\"card\"><h3>Endringer siden forrige sjekk</h3>"]
    for item in changes.get("added", [])[:25]:
        out.append(f"<div class=\"item\"><span class=\"ic chg-add\">+</span><div>"
                   f"<div>{_e(item.get('title', ''))}</div>"
                   f"<div class=\"when\">{_e(_fmt_date(item.get('date')))}</div></div></div>")
    for item in changes.get("removed", [])[:25]:
        out.append(f"<div class=\"item\"><span class=\"ic chg-del\">−</span><div>"
                   f"<div>{_e(item.get('title', ''))}</div>"
                   f"<div class=\"when\">{_e(_fmt_date(item.get('date')))}</div></div></div>")
    out.append("</div>")
    return "".join(out)
