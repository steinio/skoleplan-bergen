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


def iso_week_of(day: dt.date) -> int:
    return day.isocalendar().week
