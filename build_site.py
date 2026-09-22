#!/usr/bin/env python3
"""Build a static site: a picker for every Bergen school, plus calendar feeds.

A parent opens the page, finds their school and their child's class, and either
subscribes to a calendar or opens the school's own plan. Nothing to install and
no account -- which is the whole point of publishing it this way.

Entries are tiered honestly, because a calendar entry on the wrong day is worse
than no calendar entry:

  kalender  parsed with dates we trust  -> an .ics feed is generated
  plan      parsed, but the document never says which week -> link only
  pdf       the school publishes PDFs   -> link to the newest file
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import pathlib
import re
import sys

from schoolplan import bergen, render_ics
from schoolplan.dates import parse_bound
from schoolplan.fetch import get
from schoolplan.parse import parse_document

TIER_ICS, TIER_PLAN, TIER_PDF = "kalender", "plan", "pdf"

# A static file cannot read a query string, so each window is its own file and
# the page swaps the link. The unsuffixed one is the default, which keeps any
# existing subscription working.
WINDOWS = [
    ("maned", "Denne måneden", "7d", "30d"),
    ("", "Neste 4 måneder", "7d", "120d"),
    ("alt", "Hele skoleåret", None, None),
]
DEFAULT_WINDOW = ""


def _e(text: str) -> str:
    return html.escape(text or "", quote=True)


def build_entry(school: dict, entry: dict, out_dir: pathlib.Path, log) -> dict | None:
    """Parse one entry and, when the dates are trustworthy, write its .ics."""
    name = entry.get("klasse") or (f"{entry['trinn']}. trinn" if entry.get("trinn") else None)
    label = entry.get("label") or name or "Plan"

    if entry["kind"] == bergen.PDF:
        return {"tier": TIER_PDF, "name": name or label, "label": label,
                "url": entry["url"], "week": entry.get("week")}

    try:
        plan = parse_document(get(entry["url"]), name or school["slug"],
                              source_url=entry["url"], index_url=school["url"],
                              known_week=entry.get("week"))
    except Exception as exc:
        log(f"    ! {school['slug']}/{label}: {exc}")
        return None

    dated = [h for h in plan.highlights if h.date]
    if not dated:
        return {"tier": TIER_PLAN, "name": name or label, "label": label,
                "url": entry["url"], "week": None}

    stem = f"{school['slug']}-{entry['slug']}"
    (out_dir / "ics").mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for suffix, _, since, until in WINDOWS:
        start, end = parse_bound(since, default_sign=-1), parse_bound(until)
        text = render_ics.render(plan, start=start, end=end)
        name_ics = f"{stem}-{suffix}.ics" if suffix else f"{stem}.ics"
        (out_dir / "ics" / name_ics).write_text(text, encoding="utf-8")
        counts[suffix] = text.count("BEGIN:VEVENT")
    return {"tier": TIER_ICS, "name": name or label, "label": label,
            "url": entry["url"], "ics": f"ics/{stem}.ics", "ics_base": f"ics/{stem}",
            "events": counts.get(DEFAULT_WINDOW, len(dated)), "counts": counts,
            "week": None}


def _dedupe(results: list[dict]) -> list[dict]:
    """One row per class/trinn, keeping the newest week for PDF entries."""
    best: dict[str, dict] = {}
    for row in results:
        key = row["name"].lower()
        current = best.get(key)
        if current is None:
            best[key] = row
        elif row["tier"] == current["tier"] == TIER_PDF:
            if (row.get("week") or 0) > (current.get("week") or 0):
                best[key] = row
        elif [TIER_ICS, TIER_PLAN, TIER_PDF].index(row["tier"]) < \
             [TIER_ICS, TIER_PLAN, TIER_PDF].index(current["tier"]):
            best[key] = row
    return sorted(best.values(), key=lambda r: _sort_key(r["name"]))


def _sort_key(name: str):
    m = re.match(r"\s*(\d{1,2})\s*(.*)$", name)
    return (int(m.group(1)), m.group(2).lower()) if m else (99, name.lower())


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#15181d;--muted:#5d6672;--line:#e3e7ec;
 --accent:#1f6feb;--chip:#eef2f7;--ok:#0d8a5f;--warn:#a05a00}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#171a21;--ink:#e8eaed;
 --muted:#9aa4b2;--line:#272c36;--accent:#5a9cff;--chip:#222735;--ok:#45c99a;--warn:#e0a45c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:16px}
h1{font-size:1.5rem;margin:8px 0 4px}
.sub{color:var(--muted);font-size:.9rem;margin:0 0 16px}
.sub a{color:var(--accent)}
input[type=search]{width:100%;padding:11px 13px;font-size:1rem;border-radius:10px;
 border:1px solid var(--line);background:var(--card);color:var(--ink);margin-bottom:10px}
.window{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 14px;
 font-size:.88rem;color:var(--muted)}
.window select{padding:7px 10px;font-size:.9rem;border-radius:8px;
 border:1px solid var(--line);background:var(--card);color:var(--ink)}
details{background:var(--card);border:1px solid var(--line);border-radius:12px;
 margin-bottom:9px;overflow:hidden}
summary{padding:13px 15px;cursor:pointer;font-weight:600;list-style:none;display:flex;
 justify-content:space-between;gap:10px;align-items:center}
summary::-webkit-details-marker{display:none}
.count{font-weight:400;color:var(--muted);font-size:.82rem}
.rows{padding:0 15px 10px}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:9px 0;
 border-top:1px solid var(--line)}
.row b{min-width:80px}
.spacer{flex:1}
a.btn{display:inline-block;padding:5px 11px;border-radius:99px;font-size:.82rem;
 text-decoration:none;border:1px solid var(--line);color:var(--ink);background:var(--chip)}
a.btn.cal{background:var(--accent);border-color:var(--accent);color:#fff}
.note{font-size:.76rem;color:var(--muted)}
.legend{font-size:.82rem;color:var(--muted);margin:18px 0 8px}
.legend b{color:var(--ink)}
footer{color:var(--muted);font-size:.78rem;margin:28px 0 12px;text-align:center}
footer a{color:var(--accent)}
.empty{color:var(--muted);padding:12px 0}
"""

SCRIPT = """
const q=document.getElementById('q'),schools=[...document.querySelectorAll('details')];
q.addEventListener('input',()=>{const v=q.value.trim().toLowerCase();
 schools.forEach(d=>{const hit=!v||d.dataset.search.includes(v);
  d.hidden=!hit; if(v&&hit)d.open=true; if(!v)d.open=false;});});

// A static .ics cannot read a query string, so each window is a separate file
// and we just repoint the links.
const w=document.getElementById('window'),cals=[...document.querySelectorAll('a.cal[data-ics]')];
function applyWindow(){const s=w.value;
 cals.forEach(a=>{a.href=a.dataset.ics+(s?'-'+s:'')+'.ics';
  const n=a.dataset['n'+(s||'default')];
  const note=a.closest('.row').querySelector('.note');
  if(note&&n!==undefined)note.textContent=n+' hendelser';});
 try{localStorage.setItem('skoleplan-window',s);}catch(e){}}
try{const saved=localStorage.getItem('skoleplan-window');
 if(saved!==null&&[...w.options].some(o=>o.value===saved))w.value=saved;}catch(e){}
w.addEventListener('change',applyWindow); applyWindow();
"""


def render_index(site: dict) -> str:
    rows = []
    for school in site["schools"]:
        entries = school["entries"]
        if not entries:
            continue
        search = " ".join([school["name"], school["slug"]] +
                          [e["name"] for e in entries]).lower()
        cal = sum(1 for e in entries if e["tier"] == TIER_ICS)
        summary = f"{len(entries)} klasser/trinn" + (f" · {cal} med kalender" if cal else "")
        body = []
        for e in entries:
            buttons = []
            if e["tier"] == TIER_ICS:
                counts = e.get("counts", {})
                data = "".join(
                    f' data-n{suffix or "default"}="{counts.get(suffix, 0)}"'
                    for suffix, *_ in WINDOWS
                )
                buttons.append(
                    f'<a class="btn cal" data-ics="{_e(e.get("ics_base", ""))}"{data} '
                    f'href="{_e(e["ics"])}">Legg til i kalender</a>'
                )
                buttons.append(f'<a class="btn" href="{_e(e["url"])}">Åpne plan</a>')
                note = f'{e["events"]} hendelser'
            elif e["tier"] == TIER_PLAN:
                buttons.append(f'<a class="btn" href="{_e(e["url"])}">Åpne plan</a>')
                note = "planen oppgir ikke uke – ingen kalender"
            else:
                buttons.append(f'<a class="btn" href="{_e(e["url"])}">Åpne ukeplan (PDF)</a>')
                note = f'uke {e["week"]}' if e.get("week") else "PDF"
            body.append(
                f'<div class="row"><b>{_e(e["name"])}</b>'
                f'<span class="note">{_e(note)}</span><span class="spacer"></span>'
                + "".join(buttons) + "</div>"
            )
        rows.append(
            f'<details data-search="{_e(search)}"><summary>{_e(school["name"])}'
            f'<span class="count">{_e(summary)}</span></summary>'
            f'<div class="rows">{"".join(body)}</div></details>'
        )

    options = "".join(
        f'<option value="{suffix}"{" selected" if suffix == DEFAULT_WINDOW else ""}>'
        f'{_e(title)}</option>'
        for suffix, title, *_ in WINDOWS
    )
    stats = site["stats"]
    return f"""<!doctype html><html lang="no"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skoleplan Bergen</title><style>{CSS}</style></head><body><div class="wrap">
<h1>Skoleplan Bergen</h1>
<p class="sub">Ukeplaner for {stats['schools']} skoler i Bergen, samlet fra skolenes egne sider.
Finn klassen til barnet ditt og legg planen i kalenderen.
Oppdatert {_e(site['built_at'][:16].replace('T', ' '))} UTC.</p>
<input id="q" type="search" placeholder="Søk etter skole eller klasse…" autocomplete="off">
<div class="window"><label for="window">Periode i kalenderen:</label>
<select id="window">{options}</select>
<span>velg før du abonnerer</span></div>
{''.join(rows) or '<p class="empty">Ingen skoler funnet.</p>'}
<p class="legend"><b>Legg til i kalender</b> – abonnér, så dukker lekser, prøver,
turer og fridager opp automatisk. <b>Åpne plan</b> – skolens eget dokument.
Noen skoler skriver ikke ukenummer i planen; da lager vi ingen kalender, fordi en
oppføring på feil dag er verre enn ingen.</p>
<p class="legend"><b>Periode</b> avgjør hvor mye som havner i kalenderen din.
Standard er en uke tilbake og fire måneder frem, så du slipper gamle timer og en
kalender full av neste sommer. Valget gjelder lenkene på denne siden — velg det
<i>før</i> du abonnerer, for perioden er bakt inn i selve kalenderfilen.</p>
<footer>Hentet automatisk fra
<a href="https://www.bergen.kommune.no/omkommunen/avdelinger/skoler">bergen.kommune.no</a>.
Uoffisiell tjeneste laget av en forelder.</footer>
</div><script>{SCRIPT}</script></body></html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalogue", default="data/catalogue.json")
    parser.add_argument("--out", default="site")
    parser.add_argument("--limit", type=int, help="only the first N schools (for testing)")
    parser.add_argument("--render-only", action="store_true",
                        help="rebuild index.html from an existing site.json")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a, file=sys.stderr))

    out_only = pathlib.Path(args.out) / "site.json"
    if args.render_only:
        site = json.loads(out_only.read_text(encoding="utf-8"))
        (pathlib.Path(args.out) / "index.html").write_text(render_index(site), encoding="utf-8")
        log(f"re-rendered {args.out}/index.html")
        print(json.dumps(site["stats"]))
        return 0

    catalogue = json.loads(pathlib.Path(args.catalogue).read_text(encoding="utf-8"))
    schools = catalogue["schools"][: args.limit] if args.limit else catalogue["schools"]
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    site = {"built_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            "schools": [], "stats": {}}
    tiers = {TIER_ICS: 0, TIER_PLAN: 0, TIER_PDF: 0}

    for school in schools:
        results = []
        for entry in school["entries"]:
            if not (entry.get("klasse") or entry.get("trinn")):
                continue  # unlabelled -- a parent could not identify it anyway
            row = build_entry(school, entry, out_dir, log)
            if row:
                results.append(row)
        results = _dedupe(results)
        for row in results:
            tiers[row["tier"]] += 1
        log(f"  {school['slug']:38} {len(results):>3} rows")
        site["schools"].append({"slug": school["slug"], "name": school["name"],
                                "url": school["url"], "entries": results})

    site["stats"] = {"schools": len(site["schools"]), **tiers}
    (out_dir / "index.html").write_text(render_index(site), encoding="utf-8")
    (out_dir / "site.json").write_text(
        json.dumps(site, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"wrote {out_dir}/: {site['stats']}")
    print(json.dumps(site["stats"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
