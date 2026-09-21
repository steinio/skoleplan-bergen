"""Compare two scrapes so a run can report what the school actually changed."""

from __future__ import annotations

from .model import Highlight, Plan


def _key(item: Highlight) -> tuple:
    return (item.date or "", item.start or "", item.category, item.title.strip().lower())


def _as_row(item: Highlight) -> dict:
    return {
        "date": item.date,
        "day": item.day,
        "week": item.week,
        "start": item.start,
        "category": item.category,
        "title": item.title,
        "detail": item.detail,
    }


def compare(old: Plan | None, new: Plan) -> dict:
    """Return added/removed highlights between two plans.

    Only highlights are diffed: they are the parent-facing signal, and ordinary
    lesson prose churns too much to be worth reporting.
    """
    if old is None:
        return {"added": [], "removed": [], "first_run": True}

    old_items = {_key(h): h for h in old.highlights}
    new_items = {_key(h): h for h in new.highlights}

    added = [_as_row(new_items[k]) for k in new_items.keys() - old_items.keys()]
    removed = [_as_row(old_items[k]) for k in old_items.keys() - new_items.keys()]
    added.sort(key=lambda r: (r["date"] or "", r["start"] or ""))
    removed.sort(key=lambda r: (r["date"] or "", r["start"] or ""))
    return {"added": added, "removed": removed, "first_run": False}
