"""Fetch the school's arbeidsplaner index and the published Google Doc per class."""

from __future__ import annotations

import html
import re
import time
import urllib.error
import urllib.request

INDEX_URL = (
    "https://www.bergen.kommune.no/omkommunen/avdelinger/"
    "gimle-oppveksttun-skole/arbeidsplaner"
)

USER_AGENT = "gimle-arbeidsplan-scraper/1.0 (+personal use)"

# <a href="https://docs.google.com/document/d/e/.../pub">8E</a>
_DOC_LINK = re.compile(
    r'<a\b[^>]*href="(?P<url>https://docs\.google\.com/document/[^"]+)"[^>]*>(?P<label>.*?)</a>',
    re.I | re.S,
)
_CLASS_LABEL = re.compile(r"^\s*(\d{1,2})\s*([A-Za-zÆØÅæøå])\s*$")


def get(url: str, *, retries: int = 4, timeout: int = 45) -> str:
    """GET a URL as text, retrying transient failures with exponential backoff."""
    delay = 2.0
    last: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last = exc
            if attempt == retries - 1:
                break
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"could not fetch {url}: {last}")


def normalise_class(label: str) -> str | None:
    """"8 e" / "8E" -> "8E"; anything that is not a class label -> None."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", label))
    text = text.replace("\xa0", " ").strip()
    match = _CLASS_LABEL.match(text)
    if not match:
        return None
    return f"{int(match.group(1))}{match.group(2).upper()}"


def class_links(index_html: str) -> dict[str, str]:
    """Map class name -> published Google Doc URL, from the index page HTML."""
    links: dict[str, str] = {}
    for match in _DOC_LINK.finditer(index_html):
        name = normalise_class(match.group("label"))
        if name and name not in links:
            links[name] = html.unescape(match.group("url"))
    return links


def find_class_doc(school_class: str, index_url: str = INDEX_URL) -> tuple[str, dict[str, str]]:
    """Resolve a class name to its document URL, looking it up by link text.

    Resolving by label rather than hard-coding the URL means the scraper keeps
    working when the school republishes a document under a new id.
    """
    wanted = normalise_class(school_class) or school_class.upper()
    links = class_links(get(index_url))
    if not links:
        raise RuntimeError(f"no class document links found on {index_url}")
    if wanted not in links:
        raise RuntimeError(
            f"class {wanted!r} not found on {index_url}; available: {', '.join(sorted(links))}"
        )
    return links[wanted], links
