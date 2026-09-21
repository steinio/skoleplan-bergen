"""Turn the published Google Doc into a :class:`~schoolplan.model.Plan`.

Document shape (as published by the school):

* one table per week, whose first cell reads "Arbeidsplan for 8E / Uke: 38",
  with a time-slot column and one column per weekday;
* one "Oversiktsplan" table listing notable days for the whole term;
* trailing blank week templates, which we skip.
"""

from __future__ import annotations

import datetime as dt
import re

from .dates import (WEEKDAYS, date_for, date_in_day_header, parse_times,
                    school_year_start, strip_day_date)
from .highlights import (
    CATEGORY_LABELS,
    classify,
    primary_category,
    split_homework,
)
from . import aux
from .model import Day, Highlight, Lesson, Plan, TermEntry, Week
from .tablegrid import clean_text, tables_from_html

_WEEK_IN_CELL = re.compile(r"uke\s*:?\s*(\d{1,2})\b", re.I)
_MESSAGES_LABEL = re.compile(r"ukens\s+viktige\s+beskjeder\s*:?", re.I)
_TEACHERS_LABEL = re.compile(r"kontaktl(æ|ae)rere?\s*:?", re.I)
_DAY_NAMES = {d.lower() for d in WEEKDAYS[:5]}


def parse_document(
    document: str,
    school_class: str,
    *,
    source_url: str = "",
    index_url: str = "",
    term_start_year: int | None = None,
    today: dt.date | None = None,
    known_week: int | None = None,
) -> Plan:
    """Parse a published arbeidsplan document into structured data."""
    today = today or dt.date.today()
    term_start_year = term_start_year if term_start_year is not None else school_year_start(today)

    plan = Plan(
        school_class=school_class,
        source_url=source_url,
        index_url=index_url,
        scraped_at=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        title=f"Arbeidsplan {school_class}",
    )

    # A week stated on the school's own page ("Uke 38", "Ukeplan uke 39") is
    # authoritative -- better than anything guessed from the document.
    fallback_weeks = _weeks_mentioned(document) or [_current_week(today)]
    fallback = iter([known_week] if known_week else fallback_weeks)
    stated = known_week is not None

    # Tables are walked in document order so that an auxiliary table (homework,
    # notices) attaches to the week table it follows.
    current: Week | None = None
    for grid in tables_from_html(document):
        if _is_term_table(grid):
            plan.term.extend(_parse_term_table(grid, term_start_year))
            continue

        week = _parse_week_table(grid, term_start_year, fallback=fallback,
                                 fallback_is_stated=stated)
        if week is not None and (week.messages or any(d.lessons for d in week.days)):
            plan.weeks.append(week)
            current = week
            # Slåtthaug keeps a "LEKSER:" row inside the timetable itself.
            _attach(current, aux.lekser_row_homework(grid, _day_column_map(grid), "lekser-row"),
                    term_start_year)
            continue

        if current is not None:
            _attach(current, aux.find_homework(grid, _day_column_map(grid), "aux-table"),
                    term_start_year)
            for message in aux.messages(grid):
                if message not in current.messages:
                    current.messages.append(message)

    plan.weeks = _dedupe_weeks(plan.weeks)
    plan.weeks.sort(key=lambda w: (w.year, w.week))
    plan.term.sort(key=lambda t: (t.year, t.week, t.date or ""))
    plan.highlights = build_highlights(plan)
    return plan


# --------------------------------------------------------------------------- weeks


def _day_column_map(grid: list[list[str]]) -> dict[int, str]:
    """Column index -> weekday name, from a table's header row."""
    header = _find_header_row(grid)
    if header is None:
        return {}
    return {index: name for index, name, _, _, _ in _day_columns(grid[header])}


def _attach(week: Week, items: list, term_start_year: int) -> None:
    """Date each homework item against its week and add it, without duplicates."""
    existing = {(h.day, h.subject, h.text) for h in week.homework}
    for item in items:
        key = (item.day, item.subject, item.text)
        if key in existing:
            continue
        existing.add(key)
        if item.day and not week.inferred_week:
            item.date = _iso(date_for(week.week, item.day, term_start_year))
        week.homework.append(item)


def _parse_week_table(grid: list[list[str]], term_start_year: int, *,
                      fallback=None, fallback_is_stated: bool = False) -> Week | None:
    if not grid:
        return None

    # The weekday header row is the real signal that this is a timetable; only
    # Gimle-style documents also carry a "Uke: NN" marker inside the table.
    header_row = _find_header_row(grid)
    if header_row is None:
        return None

    week_number = _week_number(grid)
    inferred = week_number is None
    if inferred and fallback is not None:
        week_number = next(fallback, None)
        if fallback_is_stated and week_number is not None:
            inferred = False  # the school's own page named this week

    columns = _day_columns(grid[header_row], term_start_year)
    if not columns:
        return None
    if week_number is None and not any(when for *_, when in columns):
        return None

    # An explicit date in the header beats any week number: it gives the week.
    explicit = next((when for *_, when in columns if when), None)
    if explicit is not None:
        week_number = explicit.isocalendar().week
        inferred = False

    days = [
        Day(
            name=name,
            date=_iso(when or date_for(week_number, name, term_start_year)),
            starts=starts,
            ends=ends,
        )
        for _, name, starts, ends, when in columns
    ]

    body = [row for row in grid[header_row + 1:] if not _TEACHERS_LABEL.search(row[0] or "")]
    for day, (col_index, _, _, _, _) in zip(days, columns):
        day.lessons = _lessons_for_column(body, col_index, day)

    return Week(
        week=week_number,
        inferred_week=inferred,
        year=days[0].date and int(days[0].date[:4]) or term_start_year,
        monday=min((d.date for d in days if d.date), default=None),
        friday=max((d.date for d in days if d.date), default=None),
        messages=_week_messages(grid),
        teachers=_teachers(grid),
        days=days,
    )


def _lessons_for_column(body: list[list[str]], col: int, day: Day) -> list[Lesson]:
    """Collapse a column of the grid into lessons, merging repeated (spanned) cells."""
    lessons: list[Lesson] = []
    run_text: str | None = None
    run_rows: list[list[str]] = []

    def flush() -> None:
        if run_text and run_rows:
            lesson = _make_lesson(run_text, run_rows, day)
            if lesson is not None:
                lessons.append(lesson)

    for row in body:
        text = (row[col] if col < len(row) else "").strip()
        if text != run_text:
            flush()
            run_text, run_rows = text, []
        run_rows.append(row)
    flush()
    return lessons


def _make_lesson(text: str, rows: list[list[str]], day: Day) -> Lesson | None:
    if not text.strip():
        return None
    start, end = _time_span(rows)
    lines = [line for line in text.split("\n") if line.strip()]
    subject = lines[0].strip()
    homework, detail_lines = split_homework(lines[1:])
    detail = " ".join(detail_lines).strip()

    tags = classify(text)
    if homework and "homework" not in tags:
        tags.insert(0, "homework")

    return Lesson(
        day=day.name,
        date=day.date,
        start=start,
        end=end,
        subject=subject,
        detail=detail,
        homework=homework,
        tags=tags,
    )


def _time_span(rows: list[list[str]]) -> tuple[str | None, str | None]:
    """Earliest start and latest end across the slot labels a lesson covers."""
    starts: list[str] = []
    ends: list[str] = []
    for row in rows:
        start, end = parse_times(row[0] if row else "")
        if start:
            starts.append(start)
        if end:
            ends.append(end)
        elif start:
            ends.append(start)
    if not starts:
        return None, None
    return min(starts), (max(ends) if ends else None)


def _weeks_mentioned(document: str) -> list[int]:
    """Week numbers written anywhere in the document, in order of appearance."""
    text = re.sub(r"<[^>]+>", " ", document)
    out: list[int] = []
    for match in re.finditer(r"\buke\s*:?\s*(\d{1,2})\b", text, re.I):
        number = int(match.group(1))
        if 1 <= number <= 53 and number not in out:
            out.append(number)
    return out


def _current_week(today: dt.date) -> int:
    return today.isocalendar().week


def _week_number(grid: list[list[str]]) -> int | None:
    for row in grid[:3]:
        for cell in row:
            match = _WEEK_IN_CELL.search(cell or "")
            if match:
                number = int(match.group(1))
                if 1 <= number <= 53:
                    return number
    return None


def _find_header_row(grid: list[list[str]]) -> int | None:
    for index, row in enumerate(grid):
        names = set()
        for cell in row:
            first = (cell or "").split("\n")[0].strip().lower().split()
            if first:
                names.add(first[0].strip(".,:"))
        if len(names & _DAY_NAMES) >= 3:
            return index
    return None


def _day_columns(header: list[str], term_start_year: int | None = None
                 ) -> list[tuple[int, str, str | None, str | None, dt.date | None]]:
    """Return (column, day name, day start, day end, explicit date) per weekday."""
    columns = []
    seen: set[str] = set()
    for index, cell in enumerate(header):
        lines = [line.strip() for line in (cell or "").split("\n") if line.strip()]
        if not lines or not lines[0].lower().split()[0:1]:
            continue
        first = lines[0].lower().split()[0].strip(".,:")
        if first not in _DAY_NAMES or first in seen:
            continue
        seen.add(first)
        # "Mandag 21.9" carries a date; strip it before reading the day's hours,
        # or "21.09" would be misread as 21:09.
        when = date_in_day_header(cell, term_start_year)
        rest = strip_day_date(" ".join(lines)) if when else " ".join(lines[1:])
        starts, ends = parse_times(rest)
        columns.append((index, first.capitalize(), starts, ends, when))
    return columns


def _week_messages(grid: list[list[str]]) -> list[str]:
    for row in grid[:3]:
        for cell in row:
            if cell and _MESSAGES_LABEL.search(cell):
                body = _MESSAGES_LABEL.sub("", cell, count=1)
                lines = (line.strip(" -•\t") for line in body.split("\n"))
                return [line for line in lines if _is_meaningful(line)]
    return []


def _teachers(grid: list[list[str]]) -> str:
    for row in reversed(grid):
        for cell in row:
            if cell and _TEACHERS_LABEL.search(cell):
                return clean_text(_TEACHERS_LABEL.sub("", cell, count=1)).strip(" :")
    return ""


# ---------------------------------------------------------------------- oversiktsplan


def _is_meaningful(text: str) -> bool:
    """Ignore stray punctuation cells ("!", "-") left behind in the template."""
    return len(re.findall(r"[A-Za-zÆØÅæøå0-9]", text or "")) >= 2


def _split_notes(text: str) -> list[str]:
    """One overview cell may stack several notes on separate lines."""
    return [line.strip() for line in (text or "").split("\n") if _is_meaningful(line)]


def _is_term_table(grid: list[list[str]]) -> bool:
    """The Oversiktsplan table starts with a literal "Uke" header cell."""
    if not grid or not grid[0]:
        return False
    first = (grid[0][0] or "").strip().lower()
    day_cells = {(c or "").strip().lower() for c in grid[0][1:]}
    return first == "uke" and len(day_cells & _DAY_NAMES) >= 3


def _parse_term_table(grid: list[list[str]], term_start_year: int) -> list[TermEntry]:
    header = [(c or "").strip().capitalize() for c in grid[0]]
    entries: list[TermEntry] = []

    for row in grid[1:]:
        if not row or not row[0].strip().isdigit():
            continue
        week = int(row[0].strip())
        cells = row[1:]
        # A note repeated across every day (e.g. "Høstferie") spans the whole week.
        filled = [c.strip() for c in cells if c.strip()]
        whole_week = len(filled) == len(cells) and len(set(filled)) == 1 and len(cells) > 1

        if whole_week:
            for note in _split_notes(filled[0]):
                entries.append(
                    TermEntry(
                        week=week,
                        year=_year_of(week, term_start_year),
                        day=None,
                        date=_iso(date_for(week, "Mandag", term_start_year)),
                        text=note,
                        tags=classify(note) or ["notice"],
                    )
                )
            continue

        seen: set[tuple[int, str]] = set()
        for offset, cell in enumerate(cells, start=1):
            text = (cell or "").strip()
            if not text or (offset, text) in seen:
                continue
            seen.add((offset, text))
            day_name = header[offset] if offset < len(header) else None
            if not day_name or day_name.lower() not in _DAY_NAMES:
                continue
            for note in _split_notes(text):
                entries.append(
                    TermEntry(
                        week=week,
                        year=_year_of(week, term_start_year),
                        day=day_name,
                        date=_iso(date_for(week, day_name, term_start_year)),
                        text=note,
                        tags=classify(note) or ["notice"],
                    )
                )
    return entries


# ------------------------------------------------------------------------ highlights


def build_highlights(plan: Plan) -> list[Highlight]:
    """Collect everything outside the ordinary rhythm, newest-first by date."""
    out: list[Highlight] = []

    for week in plan.weeks:
        for message in week.messages:
            out.append(
                Highlight(
                    date=week.monday,
                    day=None,
                    week=week.week,
                    start=None,
                    end=None,
                    category=primary_category(message, "notice"),
                    title=message,
                    detail="Ukens viktige beskjeder",
                    source="ukeplan",
                )
            )
        if week.inferred_week:
            # The week number was guessed, so every date derived from it is a
            # guess too. Better no calendar entry than one on the wrong day.
            continue
        for item in week.homework:
            title = f"{item.subject}: {item.text}" if item.subject else item.text
            out.append(
                Highlight(
                    date=item.date or week.monday,
                    day=item.day,
                    week=week.week,
                    start=None,
                    end=None,
                    category="homework",
                    title=title,
                    detail="Hjemmearbeid",
                    source="ukeplan",
                )
            )
        for day in week.days:
            for lesson in day.lessons:
                out.extend(_lesson_highlights(week, day, lesson))

    for entry in plan.term:
        out.append(
            Highlight(
                date=entry.date,
                day=entry.day,
                week=entry.week,
                start=None,
                end=None,
                category=entry.tags[0] if entry.tags else "notice",
                title=entry.text,
                detail="Oversiktsplan" + ("" if entry.day else " (hele uken)"),
                source="oversiktsplan",
                all_week=entry.day is None,
            )
        )

    out.sort(key=lambda h: (h.date or "9999", h.start or "", h.title))
    return _dedupe(out)


def _lesson_highlights(week: Week, day: Day, lesson: Lesson) -> list[Highlight]:
    found: list[Highlight] = []
    for item in lesson.homework:
        found.append(
            Highlight(
                date=lesson.date,
                day=day.name,
                week=week.week,
                start=lesson.start,
                end=lesson.end,
                category="homework",
                title=f"{lesson.subject}: {item}",
                detail=lesson.detail,
                source="ukeplan",
            )
        )

    notable = [t for t in lesson.tags if t != "homework"]
    if notable:
        found.append(
            Highlight(
                date=lesson.date,
                day=day.name,
                week=week.week,
                start=lesson.start,
                end=lesson.end,
                category=notable[0],
                title=lesson.subject,
                detail=lesson.detail,
                source="ukeplan",
            )
        )
    return found


def _dedupe_weeks(weeks: list[Week]) -> list[Week]:
    """Keep one table per week number, preferring the one that stated it.

    Schools often pre-fill upcoming weeks with the recurring timetable and no
    "Uke: NN" yet, which the fallback would otherwise number as a duplicate.
    """
    best: dict[tuple[int, int], Week] = {}
    for week in weeks:
        key = (week.year, week.week)
        current = best.get(key)
        if current is None or (current.inferred_week and not week.inferred_week):
            best[key] = week
    return list(best.values())


def _dedupe(items: list[Highlight]) -> list[Highlight]:
    seen: set[tuple] = set()
    out: list[Highlight] = []
    for item in items:
        key = (item.date, item.start, item.category, item.title.lower().strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _year_of(week: int, term_start_year: int) -> int:
    from .dates import year_for_week

    return year_for_week(week, term_start_year)


def _iso(value: dt.date | None) -> str | None:
    return value.isoformat() if value else None


__all__ = ["parse_document", "build_highlights", "CATEGORY_LABELS"]
