"""Render highlights as an iCalendar feed you can subscribe to from a phone.

Subscribing (rather than importing) means the calendar re-reads the file and
picks up changes; UIDs are derived from the event's content position so a
revised plan updates the existing entry instead of duplicating it.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from .highlights import CATEGORY_EMOJI, CATEGORY_LABELS
from .model import Highlight, Plan

TZID = "Europe/Oslo"
UID_NAMESPACE = "gimle-arbeidsplan"

# Europe/Oslo: CET/CEST, EU rules (last Sunday in March / October).
_VTIMEZONE = f"""BEGIN:VTIMEZONE
TZID:{TZID}
X-LIC-LOCATION:{TZID}
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE"""


def escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold(line: str) -> str:
    """Fold to 75 octets per RFC 5545, splitting on encoded-byte boundaries."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks: list[bytes] = []
    start, limit = 0, 75
    while start < len(raw):
        end = min(start + limit, len(raw))
        while end > start and end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1  # do not split a multi-byte character
        chunks.append(raw[start:end])
        start, limit = end, 74
    return "\r\n ".join(chunk.decode("utf-8") for chunk in chunks)


def _stamp(plan: Plan) -> str:
    """DTSTAMP from the scrape time, so an unchanged plan renders identical bytes."""
    try:
        when = dt.datetime.fromisoformat(plan.scraped_at)
    except (TypeError, ValueError):
        when = dt.datetime.now(dt.timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return when.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _uid(plan: Plan, item: Highlight) -> str:
    key = "|".join(
        [plan.school_class, str(item.week), item.date or "", item.start or "",
         item.category, item.title.strip().lower()]
    )
    return f"{hashlib.sha1(key.encode('utf-8')).hexdigest()}@{UID_NAMESPACE}"


def _summary(item: Highlight) -> str:
    emoji = CATEGORY_EMOJI.get(item.category, "📌")
    title = item.title.strip()
    if item.category == "homework" and not title.lower().startswith("lekse"):
        title = f"Lekse – {title}"
    return f"{emoji} {title}"


def _description(item: Highlight, plan: Plan) -> str:
    parts = [CATEGORY_LABELS.get(item.category, item.category)]
    if item.detail:
        parts.append(item.detail)
    if item.day:
        parts.append(f"{item.day}, uke {item.week}")
    else:
        parts.append(f"Uke {item.week}")
    parts.append(plan.source_url)
    return "\n".join(p for p in parts if p)


def render(plan: Plan, *, categories: tuple[str, ...] | None = None,
           alarm_hours: int = 15) -> str:
    """Build the .ics text. ``alarm_hours`` sets a reminder before homework."""
    stamp = _stamp(plan)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{UID_NAMESPACE}//{plan.school_class}//NO",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:Arbeidsplan {plan.school_class}",
        f"X-WR-TIMEZONE:{TZID}",
        f"X-WR-CALDESC:Lekser, prøver, turer og fridager for {plan.school_class} "
        f"ved Gimle oppveksttun skole",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
        *_VTIMEZONE.split("\n"),
    ]

    for item in plan.highlights:
        if not item.date:
            continue
        if categories and item.category not in categories:
            continue
        lines.extend(_event(plan, item, stamp, alarm_hours))

    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"


def _event(plan: Plan, item: Highlight, stamp: str, alarm_hours: int) -> list[str]:
    start = dt.date.fromisoformat(item.date)
    out = [
        "BEGIN:VEVENT",
        f"UID:{_uid(plan, item)}",
        f"DTSTAMP:{stamp}",
        f"SUMMARY:{escape(_summary(item))}",
        f"DESCRIPTION:{escape(_description(item, plan))}",
        f"CATEGORIES:{escape(CATEGORY_LABELS.get(item.category, item.category))}",
        f"URL:{escape(plan.source_url)}",
        "TRANSP:TRANSPARENT",
    ]

    if item.start:
        begin = dt.datetime.combine(start, dt.time.fromisoformat(item.start))
        finish = (
            dt.datetime.combine(start, dt.time.fromisoformat(item.end))
            if item.end and item.end > item.start
            else begin + dt.timedelta(minutes=45)
        )
        out.append(f"DTSTART;TZID={TZID}:{begin.strftime('%Y%m%dT%H%M%S')}")
        out.append(f"DTEND;TZID={TZID}:{finish.strftime('%Y%m%dT%H%M%S')}")
    else:
        span = 5 if item.all_week else 1
        out.append(f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}")
        out.append(f"DTEND;VALUE=DATE:{(start + dt.timedelta(days=span)).strftime('%Y%m%d')}")

    if item.category == "homework" and alarm_hours > 0:
        out.extend(
            [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{escape(_summary(item))}",
                f"TRIGGER:-PT{alarm_hours}H",
                "END:VALARM",
            ]
        )

    out.append("END:VEVENT")
    return out
