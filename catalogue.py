#!/usr/bin/env python3
"""Survey every Bergen school and write a catalogue of subscribable plans.

The catalogue is what lets a parent find their own child's plan: it lists each
school, how that school publishes, and every plan entry discovered on its pages.

  ./catalogue.py                      # survey all Bergen schools -> data/catalogue.json
  ./catalogue.py --school gimle-oppveksttun-skole
  ./catalogue.py --limit 10           # quick sample while developing
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import datetime as dt
import json
import pathlib
import sys
from dataclasses import asdict

from schoolplan import bergen


def build(slugs: list[str], workers: int = 4, log=print) -> dict:
    schools: list[bergen.School] = []
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for school in pool.map(_safe_survey, slugs):
            if school is None:
                continue
            schools.append(school)
            log(f"  {school.slug:38} {len(school.entries):>3} entries  {sorted(school.kinds)}")

    schools.sort(key=lambda s: s.slug)
    return {
        "kommune": bergen.KOMMUNE,
        "built_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "schools": [
            {
                "slug": s.slug,
                "name": s.name,
                "url": s.url,
                "kinds": sorted(s.kinds),
                "entries": [
                    {**asdict(e), "slug": e.slug}
                    for e in s.entries
                    # PDF entries have no label until the file is fetched; keep
                    # them anyway so the school is not shown as empty.
                ],
            }
            for s in schools
        ],
    }


def _safe_survey(slug: str):
    try:
        return bergen.survey_school(slug)
    except Exception as exc:  # a single bad school must not sink the survey
        print(f"  ! {slug}: {exc}", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--school", action="append", help="survey only this slug (repeatable)")
    parser.add_argument("--limit", type=int, help="only the first N schools")
    parser.add_argument("--out", default="data/catalogue.json")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a, file=sys.stderr))

    slugs = args.school or bergen.list_schools()
    if args.limit:
        slugs = slugs[: args.limit]
    log(f"surveying {len(slugs)} school(s)")

    catalogue = build(slugs, workers=args.workers, log=log)

    path = pathlib.Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalogue, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    kinds: dict[str, int] = {}
    entries = 0
    for s in catalogue["schools"]:
        entries += len(s["entries"])
        for k in s["kinds"] or ["none"]:
            kinds[k] = kinds.get(k, 0) + 1
    log(f"wrote {path}: {len(catalogue['schools'])} schools, {entries} entries, {kinds}")
    print(f"{len(catalogue['schools'])} schools, {entries} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
