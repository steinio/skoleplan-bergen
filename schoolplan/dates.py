"""Map Norwegian week numbers and weekday names onto real calendar dates.

The plan documents only ever say "Uke 38" / "Mandag".  A Norwegian school year
runs from August to June, so weeks >= 30 belong to the year the term started and
weeks < 30 to the year after.
"""

from __future__ import annotations

import datetime as dt
import re

WEEKDAYS = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]
_WEEKDAY_INDEX = {name.lower(): i + 1 for i, name in enumerate(WEEKDAYS)}

# Week numbers at or above this belong to the autumn half of the school year.
AUTUMN_CUTOFF_WEEK = 30


def school_year_start(today: dt.date | None = None) -> int:
    """Return the calendar year in which the current school year began."""
    today = today or dt.date.today()
    return today.year if today.month >= 8 else today.year - 1


def year_for_week(week: int, term_start_year: int | None = None) -> int:
    """Calendar year that ``week`` falls in, for the school year starting then."""
    start = term_start_year if term_start_year is not None else school_year_start()
    return start if week >= AUTUMN_CUTOFF_WEEK else start + 1


def date_for(week: int, weekday: str | int, term_start_year: int | None = None) -> dt.date | None:
    """Resolve (week number, weekday) to a date, or None if it cannot be placed."""
    if isinstance(weekday, str):
        index = _WEEKDAY_INDEX.get(weekday.strip().lower())
    else:
        index = weekday
    if not index or not 1 <= index <= 7 or not 1 <= week <= 53:
        return None
    try:
        return dt.date.fromisocalendar(year_for_week(week, term_start_year), week, index)
    except ValueError:
        return None


def parse_times(slot: str) -> tuple[str | None, str | None]:
    """Pull the start and end time out of a row label.

    The documents are inconsistent -- "08.30 - 09.00", "09:40-10:10" and even the
    typo "11:40.12:10" all occur -- so we just collect every time-like token.
    """
    found = re.findall(r"(\d{1,2})[:.](\d{2})", slot or "")
    times = [f"{int(h):02d}:{m}" for h, m in found if int(h) <= 23 and int(m) <= 59]
    if not times:
        return None, None
    return times[0], (times[-1] if len(times) > 1 else None)


MONTHS = {
    "januar": 1, "februar": 2, "mars": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11,
    "desember": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "okt": 10, "nov": 11, "des": 12,
}

# "Mandag 21.9", "Tirsdag 22/9", "Onsdag 23.09.26" -- the weekday name is what
# makes this unambiguous; a bare "11.10" could equally be a time.
_DAY_WITH_DATE = re.compile(
    rf"\b({'|'.join(d.lower() for d in WEEKDAYS[:7])})\b[^\d\n]{{0,12}}"
    r"(\d{1,2})\s*[./]\s*(\d{1,2})(?:\s*[./]\s*(\d{2,4}))?",
    re.I,
)
_DAY_WITH_MONTH_NAME = re.compile(
    rf"\b({'|'.join(d.lower() for d in WEEKDAYS[:7])})\b[^\d\n]{{0,12}}"
    rf"(\d{{1,2}})\.?\s*({'|'.join(MONTHS)})",
    re.I,
)


def date_in_day_header(text: str, term_start_year: int | None = None) -> dt.date | None:
    """Read an explicit date out of a day-header cell such as "Mandag 21.9".

    Returns None unless a weekday name sits right next to the number, because
    without it "11.10" is as likely to be a time as a date.
    """
    start = term_start_year if term_start_year is not None else school_year_start()

    match = _DAY_WITH_MONTH_NAME.search(text or "")
    if match:
        day, month = int(match.group(2)), MONTHS[match.group(3).lower()]
        return _make(day, month, None, start)

    match = _DAY_WITH_DATE.search(text or "")
    if match:
        day, month = int(match.group(2)), int(match.group(3))
        return _make(day, month, match.group(4), start)
    return None


def strip_day_date(text: str) -> str:
    """Remove a "Mandag 21.9" date so the remaining times can be read safely."""
    without = _DAY_WITH_MONTH_NAME.sub(" ", text or "")
    return _DAY_WITH_DATE.sub(" ", without)


def _make(day: int, month: int, year_text: str | None, start: int) -> dt.date | None:
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None
    if year_text:
        year = int(year_text)
        year += 2000 if year < 100 else 0
    else:
        # August onwards belongs to the year the school year began.
        year = start if month >= 8 else start + 1
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def iso_week_of(day: dt.date) -> int:
    return day.isocalendar().week
