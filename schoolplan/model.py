"""Dataclasses describing a parsed arbeidsplan, plus JSON (de)serialisation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Lesson:
    """One block in the weekly grid: a subject, what they do, and any homework."""

    day: str                      # "Mandag" ... "Fredag"
    date: str | None              # ISO date, resolved from the week number
    start: str | None             # "09:40"
    end: str | None               # "10:40"
    subject: str                  # first line of the cell
    detail: str = ""              # remaining prose, homework lines removed
    homework: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class Homework:
    """Homework found outside a lesson cell, in an auxiliary table."""

    day: str | None           # "Tirsdag" when the table says which day
    date: str | None
    subject: str
    text: str
    source: str = ""          # which table shape it came from


@dataclass
class Day:
    name: str
    date: str | None
    starts: str | None = None     # school day start from the column header
    ends: str | None = None
    lessons: list[Lesson] = field(default_factory=list)


@dataclass
class Week:
    week: int
    year: int
    monday: str | None
    friday: str | None
    inferred_week: bool = False   # the week number was guessed, not stated in the document
    messages: list[str] = field(default_factory=list)   # "Ukens viktige beskjeder"
    homework: list[Homework] = field(default_factory=list)  # from auxiliary tables
    teachers: str = ""
    days: list[Day] = field(default_factory=list)


@dataclass
class TermEntry:
    """A cell from the Oversiktsplan (whole-term overview) table."""

    week: int
    year: int
    day: str | None               # None when the note spans the whole week
    date: str | None
    text: str
    tags: list[str] = field(default_factory=list)


@dataclass
class Highlight:
    """Anything worth surfacing: homework, a trip, a day off, a test, a meeting."""

    date: str | None
    day: str | None
    week: int
    start: str | None
    end: str | None
    category: str                 # homework | dayoff | test | trip | meeting | notice | bring
    title: str
    detail: str = ""
    source: str = ""              # "ukeplan" or "oversiktsplan"
    all_week: bool = False        # a note covering the whole week, e.g. "Høstferie"


@dataclass
class Plan:
    school_class: str
    source_url: str
    index_url: str
    scraped_at: str
    title: str = ""
    weeks: list[Week] = field(default_factory=list)
    term: list[TermEntry] = field(default_factory=list)
    highlights: list[Highlight] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Plan":
        weeks = [
            Week(
                **{
                    **w,
                    "days": [
                        Day(**{**d, "lessons": [Lesson(**le) for le in d.get("lessons", [])]})
                        for d in w.get("days", [])
                    ],
                    "homework": [Homework(**h) for h in w.get("homework", [])],
                }
            )
            for w in data.get("weeks", [])
        ]
        return Plan(
            school_class=data["school_class"],
            source_url=data.get("source_url", ""),
            index_url=data.get("index_url", ""),
            scraped_at=data.get("scraped_at", ""),
            title=data.get("title", ""),
            weeks=weeks,
            term=[TermEntry(**t) for t in data.get("term", [])],
            highlights=[Highlight(**h) for h in data.get("highlights", [])],
        )
