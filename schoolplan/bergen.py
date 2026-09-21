"""Discovery for Bergen kommune: which schools publish plans, and in what form.

All 81 Bergen schools expose an ``/arbeidsplaner`` page under the same CMS, but
they publish the plans themselves in one of two ways:

* **Google Docs** (15 schools) -- a published document per class or per trinn,
  containing the weekly table this package can parse in full.
* **PDF** (66 schools) -- one file per trinn per week, linked through the CMS's
  ``/api/rest/filer/<id>`` endpoint.

Some schools nest the links one level deeper, under a per-trinn sub-page.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from .fetch import get

BASE = "https://www.bergen.kommune.no"
SITEMAP = f"{BASE}/sitemap.xml"
KOMMUNE = "bergen"

GDOCS = "gdocs"
PDF = "pdf"

_DOC_LINK = re.compile(
    r'<a\b[^>]*href="(?P<url>https://docs\.google\.com/document/[^"]+)"[^>]*>(?P<label>.*?)</a>',
    re.I | re.S,
)
# The CMS renders file links with the title in attributes rather than link text.
_FILE_ANCHOR = re.compile(r'<a\b[^>]*?/api/rest/filer/[A-Za-z0-9]+[^>]*>', re.I)
_ATTR_HREF = re.compile(r'href="(/api/rest/filer/[A-Za-z0-9]+)"', re.I)
_ATTR_TITLE = re.compile(r'data-tittel="([^"]*)"', re.I)
_HEADING = re.compile(r'<h([2-4])[^>]*>(.*?)</h\1>', re.I | re.S)
_WEEK_LABEL = re.compile(r'\buke\s*:?\s*(\d{1,2})\b', re.I)
_TRINN_LABEL = re.compile(r'\b(\d{1,2})\s*\.?\s*trinn\b', re.I)
_CLASS_LABEL = re.compile(r'\b(\d{1,2})\s*[-.]?\s*([A-Za-zÆØÅæøå0-9])\b')


@dataclass
class PlanEntry:
    """One publishable plan a parent could subscribe to."""

    school: str                  # slug, e.g. "gimle-oppveksttun-skole"
    label: str                   # the link text as published
    url: str
    kind: str                    # GDOCS | PDF
    klasse: str | None = None    # "8E" when the label names a class
    trinn: int | None = None     # 8 when the label names a year group
    week: int | None = None      # 38 when the label names a week
    page: str = ""               # the page the link was found on

    @property
    def slug(self) -> str:
        """A stable, URL-safe id for this entry."""
        base = self.klasse or (f"{self.trinn}trinn" if self.trinn else None) or self.label
        base = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "plan"
        if self.week and not self.klasse and not self.trinn:
            base = f"uke-{self.week}"
        return base


@dataclass
class School:
    slug: str
    name: str = ""
    kinds: set[str] = field(default_factory=set)
    entries: list[PlanEntry] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{BASE}/omkommunen/avdelinger/{self.slug}/arbeidsplaner"


def clean_label(raw: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def list_schools(sitemap_xml: str | None = None) -> list[str]:
    """Every school slug that has an arbeidsplaner page, from the sitemap."""
    xml = sitemap_xml if sitemap_xml is not None else get(SITEMAP)
    slugs = {
        m.group(1)
        for m in re.finditer(r"/omkommunen/avdelinger/([^/<]+)/arbeidsplaner", xml)
    }
    return sorted(slugs)


def _label_facts(label: str) -> tuple[str | None, int | None, int | None]:
    """Pull a class, trinn and/or week number out of a published link label."""
    week = _WEEK_LABEL.search(label)
    trinn = _TRINN_LABEL.search(label)
    klasse = None
    if not trinn:
        # "8A", "Arbeidsplan 8A", "8-1", "8a" -- but not "Uke 38".
        stripped = _WEEK_LABEL.sub(" ", label)
        m = _CLASS_LABEL.search(stripped)
        if m and 1 <= int(m.group(1)) <= 10:
            klasse = f"{int(m.group(1))}{m.group(2).upper()}"
    return (
        klasse,
        int(trinn.group(1)) if trinn else None,
        int(week.group(1)) if week else None,
    )


def _entries_on_page(slug: str, page_url: str, page_html: str) -> list[PlanEntry]:
    out: list[PlanEntry] = []
    for m in _DOC_LINK.finditer(page_html):
        label = clean_label(m.group("label"))
        klasse, trinn, week = _label_facts(label)
        out.append(PlanEntry(slug, label, html.unescape(m.group("url")), GDOCS,
                             klasse, trinn, week, page_url))
    # PDF links carry their label in data-tittel, grouped under an <h2> naming
    # the trinn -- the visible text is written by the CMS's JS.
    headings = [(m.start(), clean_label(m.group(2))) for m in _HEADING.finditer(page_html)]
    seen: set[str] = set()
    for m in _FILE_ANCHOR.finditer(page_html):
        tag = m.group(0)
        href_match = _ATTR_HREF.search(tag)
        if not href_match:
            continue
        href = href_match.group(1)
        if href in seen:
            continue
        seen.add(href)
        title_match = _ATTR_TITLE.search(tag)
        title = clean_label(title_match.group(1) if title_match else "")
        group = ""
        for pos, text in headings:
            if pos < m.start():
                group = text
            else:
                break
        label = " – ".join(x for x in (group, title) if x)
        klasse, trinn, week = _label_facts(label)
        out.append(PlanEntry(slug, label, BASE + href, PDF, klasse, trinn, week, page_url))
    return out


def _subpages(slug: str, page_html: str) -> list[str]:
    pattern = rf'href="(/omkommunen/avdelinger/{re.escape(slug)}/arbeidsplaner/[^"#?]+)"'
    return sorted(set(re.findall(pattern, page_html)))


def survey_school(slug: str, *, follow_subpages: bool = True, max_subpages: int = 12) -> School:
    """Fetch a school's arbeidsplaner page (and its trinn sub-pages) and list plans."""
    school = School(slug=slug)
    top = school.url
    page = get(top)
    school.name = _page_title(page, slug)
    school.entries.extend(_entries_on_page(slug, top, page))

    if follow_subpages:
        for path in _subpages(slug, page)[:max_subpages]:
            school.entries.extend(_entries_on_page(slug, BASE + path, get(BASE + path)))

    school.kinds = {e.kind for e in school.entries}
    return school


def school_name(slug: str) -> str:
    """"gimle-oppveksttun-skole" -> "Gimle oppveksttun skole"."""
    words = slug.replace("_", "-").split("-")
    return " ".join([words[0].capitalize(), *words[1:]]) if words else slug


def _page_title(page_html: str, slug: str = "") -> str:
    """The school's own name, properly spelled.

    The page title is just "Bergen kommune - Arbeidsplaner", and the slug is
    ASCII ("alvoen-skole"), so neither gives "Alvøen skole". The link back to
    the school's own front page does.
    """
    link = re.search(
        rf'<a\b[^>]*href="/omkommunen/avdelinger/{re.escape(slug)}"[^>]*>(.*?)</a>',
        page_html, re.S | re.I,
    )
    if link:
        name = clean_label(link.group(1))
        if name and len(name) < 80:
            return name
    return school_name(slug)
