"""Extract homework and messages from the auxiliary tables schools use.

Gimle writes homework inline in the lesson cell ("Lekse: ..."), but most other
Bergen schools keep it in a separate table, in one of three shapes:

* **day-keyed block** -- one cell headed "Hjemmearbeid" whose text uses
  "Til tirsdag:", "Til onsdag:" as day headings (Rothaugen);
* **subject table** -- columns "Fag | Forberedelser til timen | Tema | Frister",
  one row per subject (Kirkevoll);
* **LEKSER row** -- a row inside the timetable itself, one cell per day column
  (Slåtthaug).

Messages live under headings like "Beskjeder og informasjon" or "Oppslagstavle".
"""

from __future__ import annotations

import re

from .dates import WEEKDAYS

_DAYS = [d.lower() for d in WEEKDAYS[:5]]
_DAY_SET = set(_DAYS)

# "Til tirsdag:" / "Til onsdag :" -- a day heading inside a homework cell.
_DAY_HEADING = re.compile(rf"^\s*til\s+({'|'.join(_DAYS)})\s*:?\s*$", re.I)
# "Mandag:" used the same way.
_BARE_DAY_HEADING = re.compile(rf"^\s*({'|'.join(_DAYS)})\s*:\s*$", re.I)

_HOMEWORK_HEADER = re.compile(
    r"^\s*(hjemmearbeid|lekser?|forberedelser(\s+til\s+timen)?|til\s+neste\s+time)\s*:?\s*$", re.I
)
_SUBJECT_HEADER = re.compile(r"^\s*fag\s*:?\s*$", re.I)
_DEADLINE_HEADER = re.compile(r"^\s*(frister?|innlevering(er)?)\s*:?\s*$", re.I)
_MESSAGE_HEADER = re.compile(
    r"^\s*(beskjeder(\s+og\s+informasjon)?|informasjon|oppslagstavle|ukens\s+beskjeder)\s*:?\s*$",
    re.I,
)
_MESSAGE_INLINE = re.compile(
    r"^\s*(beskjeder(\s+og\s+informasjon)?|informasjon|oppslagstavle)\s*:\s*", re.I
)
_LEKSER_LABEL = re.compile(r"^\s*lekser?\s*:?\s*$", re.I)
# Lines that look like homework but are not: time slots, bare day headings and
# the titles of other documents the school links.
_TIMEISH = re.compile(r"^[\s\d.:–—-]*$")
_DOC_TITLE = re.compile(r"^\s*(arbeidsplan|lekseplan|ukeplan|timeplan|fremdriftsplan)\b", re.I)


def _is_real_homework(line: str) -> bool:
    text = line.strip()
    if len(text) < 12 or _TIMEISH.match(text) or _DOC_TITLE.match(text):
        return False
    if _DAY_HEADING.match(text) or _BARE_DAY_HEADING.match(text):
        return False
    # "Til tirsdag", "Til mandag neste uke" -- a heading, not an assignment.
    if re.match(rf"^\s*til\s+({'|'.join(_DAYS)})\b[\w\s]{{0,14}}$", text, re.I):
        return False
    # Column headings from the subject tables.
    if re.match(r"^\s*(tema\b|gj\u00f8rem\u00e5l|forberedelser|frister?|fag)\b[\w/\s]{0,24}$",
                text, re.I):
        return False
    return len(re.findall(r"[A-Za-zÆØÅæøå]", text)) >= 8


from .model import Homework


def _mk(day: str | None, subject: str, text: str, source: str) -> Homework:
    return Homework(day=day, date=None, subject=subject, text=text, source=source)


def _lines(cell: str) -> list[str]:
    return [ln.strip() for ln in (cell or "").split("\n") if ln.strip()]


def _split_subject(line: str) -> tuple[str, str]:
    """"Matte: jobb vidare" -> ("Matte", "jobb vidare")."""
    m = re.match(r"^\s*([^:]{1,40}?)\s*:\s*(.+)$", line)
    return (m.group(1).strip(), m.group(2).strip()) if m else ("", line.strip())


def day_keyed_homework(cell: str, source: str) -> list[Homework]:
    """Parse a "Hjemmearbeid" cell that uses "Til <dag>:" headings."""
    out: list[Homework] = []
    current: str | None = None
    for line in _lines(cell):
        heading = _DAY_HEADING.match(line) or _BARE_DAY_HEADING.match(line)
        if heading:
            current = heading.group(1).capitalize()
            continue
        if _HOMEWORK_HEADER.match(line):
            continue
        subject, text = _split_subject(line)
        if text:
            out.append(_mk(current, subject, text, source))
    return out


def _header_columns(row: list[str]) -> dict[str, int]:
    """Map a logical column name to its index, from a header row."""
    found: dict[str, int] = {}
    for index, cell in enumerate(row):
        text = (cell or "").strip()
        if _SUBJECT_HEADER.match(text):
            found.setdefault("subject", index)
        elif _HOMEWORK_HEADER.match(text):
            found.setdefault("homework", index)
        elif _DEADLINE_HEADER.match(text):
            found.setdefault("deadline", index)
    return found


def subject_table_homework(grid: list[list[str]], source: str) -> list[Homework]:
    """Parse a "Fag | Forberedelser til timen | ... | Frister" table."""
    out: list[Homework] = []
    for index, row in enumerate(grid):
        columns = _header_columns(row)
        if "subject" not in columns or "homework" not in columns:
            continue
        seen: set[tuple[str, str]] = set()
        for body in grid[index + 1:]:
            if _header_columns(body).get("subject") is not None:
                break  # a second header row starts a new block
            subject = (body[columns["subject"]] if columns["subject"] < len(body) else "").strip()
            work = (body[columns["homework"]] if columns["homework"] < len(body) else "").strip()
            if not subject or not work or _SUBJECT_HEADER.match(subject):
                continue
            key = (subject, work)
            if key in seen:
                continue
            seen.add(key)
            for line in _lines(work):
                out.append(_mk(None, subject.rstrip(":"), line, source))
        break
    return out


def lekser_row_homework(grid: list[list[str]], day_columns: dict[int, str],
                        source: str) -> list[Homework]:
    """Parse a "LEKSER:" row inside a timetable, one cell per day column."""
    out: list[Homework] = []
    for row in grid:
        if not any(_LEKSER_LABEL.match((c or "").strip()) for c in row):
            continue
        seen: set[tuple[str, str]] = set()
        for column, day in day_columns.items():
            text = (row[column] if column < len(row) else "").strip()
            if not text or _LEKSER_LABEL.match(text):
                continue
            for line in _lines(text):
                subject, body = _split_subject(line)
                key = (day, line)
                if key in seen:
                    continue
                seen.add(key)
                out.append(_mk(day, subject, body, source))
        break
    return out


def messages(grid: list[list[str]]) -> list[str]:
    """Pull notices out of a "Beskjeder"/"Oppslagstavle"/"Informasjon" cell."""
    out: list[str] = []
    for row_index, row in enumerate(grid):
        for column, cell in enumerate(row):
            text = (cell or "").strip()
            if not text:
                continue
            if _MESSAGE_INLINE.match(text):
                out.extend(_lines(_MESSAGE_INLINE.sub("", text, count=1)))
            elif _MESSAGE_HEADER.match(text):
                for below in grid[row_index + 1:]:
                    body = (below[column] if column < len(below) else "").strip()
                    if body and not _MESSAGE_HEADER.match(body):
                        out.extend(_lines(body))
                        break
    seen: set[str] = set()
    unique = []
    for line in out:
        key = line.lower()
        if key not in seen and len(line) > 2:
            seen.add(key)
            unique.append(line)
    return unique


def label_block_homework(grid: list[list[str]], source: str) -> list[Homework]:
    """Parse a "Lekser:" / "Hjemmearbeid" label cell with its text alongside.

    Rå, Rådalslien and Skranevatnet head a cell "Lekser:" and put the work in
    the neighbouring cells -- to the right, or underneath -- as "Fag: oppgave"
    lines, with no day columns to key on.
    """
    out: list[Homework] = []
    seen: set[tuple[str, str]] = set()
    for row_index, row in enumerate(grid):
        for column, cell in enumerate(row):
            first = _lines(cell)[:1]
            if not first or not _HOMEWORK_HEADER.match(first[0]):
                continue
            # Only the cells beside the label, and the one directly beneath it.
            # Scanning the whole column sweeps in the timetable's time slots.
            neighbours = list(row[column + 1:])
            if row_index + 1 < len(grid) and column < len(grid[row_index + 1]):
                neighbours.append(grid[row_index + 1][column])
            for text in neighbours:
                for line in _lines(text):
                    if _HOMEWORK_HEADER.match(line) or _MESSAGE_HEADER.match(line):
                        continue
                    if not _is_real_homework(line):
                        continue
                    subject, body = _split_subject(line)
                    key = (subject, body)
                    if key in seen or not body:
                        continue
                    seen.add(key)
                    out.append(_mk(None, subject, body, source))
    return out


def find_homework(grid: list[list[str]], day_columns: dict[int, str],
                  source: str) -> list[Homework]:
    """Try every auxiliary shape against one table."""
    found = subject_table_homework(grid, source)
    if found:
        return found
    found = lekser_row_homework(grid, day_columns, source)
    if found:
        return found
    for row in grid:
        for cell in row:
            if not cell:
                continue
            # The headings are anchored per line, so test the lines rather than
            # searching the whole multi-line cell.
            lines = _lines(cell)
            if any(_DAY_HEADING.match(ln) or _BARE_DAY_HEADING.match(ln) for ln in lines) or (
                lines and _HOMEWORK_HEADER.match(lines[0])
            ):
                found = day_keyed_homework(cell, source)
                if found:
                    return found
    return label_block_homework(grid, source)
