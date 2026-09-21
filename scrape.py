#!/usr/bin/env python3
"""Scrape a Gimle oppveksttun skole arbeidsplan and write JSON, ICS, HTML and Markdown.

Examples
--------
  ./scrape.py                          # class 8E, writes into ./data
  ./scrape.py --class 9B --out data    # another class
  ./scrape.py --list                   # show every class the school publishes
  ./scrape.py --from-file page.html    # re-render from a saved document
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import replace

from schoolplan import diff, fetch, render_html, render_ics, render_md
from schoolplan.highlights import OUT_OF_ORDINARY
from schoolplan.model import Highlight, Plan
from schoolplan.parse import parse_document

DEFAULT_CLASS = "8E"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--class", dest="school_class", default=DEFAULT_CLASS,
                        help=f"class to scrape (default: {DEFAULT_CLASS})")
    parser.add_argument("--out", default="data", help="output directory (default: data)")
    parser.add_argument("--index-url", default=fetch.INDEX_URL,
                        help="the school's arbeidsplaner page")
    parser.add_argument("--doc-url", default=None,
                        help="skip the index lookup and use this document URL")
    parser.add_argument("--from-file", default=None,
                        help="parse a saved copy of the document instead of fetching")
    parser.add_argument("--list", action="store_true",
                        help="list the classes published on the index page and exit")
    parser.add_argument("--categories", default=",".join(OUT_OF_ORDINARY),
                        help="categories to put in the .ics feed")
    parser.add_argument("--all-lessons", action="store_true",
                        help="also emit an ics with every lesson, not just highlights")
    parser.add_argument("--term-start-year", type=int, default=None,
                        help="year the school year started (default: inferred)")
    parser.add_argument("--quiet", action="store_true", help="only print warnings")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a, file=sys.stderr))

    if args.list:
        for name, url in sorted(fetch.class_links(fetch.get(args.index_url)).items()):
            print(f"{name:>4}  {url}")
        return 0

    school_class = fetch.normalise_class(args.school_class) or args.school_class.upper()

    if args.from_file:
        document = pathlib.Path(args.from_file).read_text(encoding="utf-8")
        doc_url = args.doc_url or f"file://{pathlib.Path(args.from_file).resolve()}"
    else:
        doc_url = args.doc_url
        if not doc_url:
            log(f"looking up {school_class} on {args.index_url}")
            doc_url, found = fetch.find_class_doc(school_class, args.index_url)
            log(f"found {len(found)} classes; {school_class} -> {doc_url}")
        document = fetch.get(doc_url)

    plan = parse_document(
        document,
        school_class,
        source_url=doc_url,
        index_url=args.index_url,
        term_start_year=args.term_start_year,
    )
    log(f"parsed {len(plan.weeks)} weeks, {len(plan.term)} term entries, "
        f"{len(plan.highlights)} highlights")

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = school_class.lower()

    json_path = out_dir / f"{stem}.json"
    previous = _load_previous(json_path)
    changes = diff.compare(previous, plan)

    # Keep the old timestamp when nothing but the timestamp would change, so a
    # scheduled run that finds an untouched plan leaves the files byte-identical
    # and produces no commit.
    if previous is not None and _same_content(previous, plan):
        plan.scraped_at = previous.scraped_at

    json_path.write_text(
        json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / f"{stem}.ics").write_text(
        render_ics.render(plan, categories=tuple(
            c.strip() for c in args.categories.split(",") if c.strip())),
        encoding="utf-8",
    )
    (out_dir / f"{stem}.html").write_text(
        render_html.render(plan, changes=changes, ics_url=f"{stem}.ics"), encoding="utf-8"
    )
    (out_dir / f"{stem}.md").write_text(render_md.render(plan), encoding="utf-8")
    (out_dir / f"{stem}.changes.json").write_text(
        json.dumps(changes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if args.all_lessons:
        (out_dir / f"{stem}-alle-timer.ics").write_text(
            render_ics.render(_lessons_as_highlights(plan), alarm_hours=0), encoding="utf-8"
        )

    summary = render_md.summarise_changes(changes)
    log(f"wrote {json_path.parent}/ ({summary})")
    print(summary)
    return 0


def _same_content(old: Plan, new: Plan) -> bool:
    """True when two scrapes differ only in when they were taken."""
    left, right = old.to_dict(), new.to_dict()
    left.pop("scraped_at", None)
    right.pop("scraped_at", None)
    return left == right


def _load_previous(path: pathlib.Path) -> Plan | None:
    if not path.exists():
        return None
    try:
        return Plan.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, KeyError, TypeError) as exc:
        print(f"warning: ignoring unreadable {path}: {exc}", file=sys.stderr)
        return None


def _lessons_as_highlights(plan: Plan) -> Plan:
    """A copy of the plan whose highlights are every lesson (full timetable feed)."""
    items: list[Highlight] = []
    for week in plan.weeks:
        for day in week.days:
            for lesson in day.lessons:
                items.append(
                    Highlight(
                        date=lesson.date, day=day.name, week=week.week,
                        start=lesson.start, end=lesson.end,
                        category=lesson.tags[0] if lesson.tags else "notice",
                        title=lesson.subject, detail=lesson.detail, source="ukeplan",
                    )
                )
    return replace(plan, highlights=items)


if __name__ == "__main__":
    raise SystemExit(main())
