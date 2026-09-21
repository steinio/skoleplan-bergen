"""Turn the <table> elements of an HTML document into dense 2-D string grids.

Google Docs exports its tables with liberal ``rowspan``/``colspan``, so a naive
row-by-row read misaligns the day columns.  ``tables_from_html`` expands every
span so that grid[row][col] always holds the text of the cell covering that
position -- a merged cell simply repeats.  Stdlib only, no third-party parser.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# Tags that imply a line break when we flatten a cell's inline content.
_BLOCK_TAGS = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}


class _TableCollector(HTMLParser):
    """Collect top-level tables as lists of rows of raw cell descriptors."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[dict]]] = []
        self._depth = 0
        self._rows: list[list[dict]] | None = None
        self._row: list[dict] | None = None
        self._cell: dict | None = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
            return
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._rows = []
            return
        if self._depth != 1:
            return
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            values = dict(attrs)

            def span(key: str) -> int:
                try:
                    return max(1, int(values.get(key, "1")))
                except (TypeError, ValueError):
                    return 1

            self._cell = {"rowspan": span("rowspan"), "colspan": span("colspan"), "parts": []}
        elif tag in _BLOCK_TAGS and self._cell is not None:
            self._cell["parts"].append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and self._cell is not None:
            self._cell["parts"].append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
            return
        if tag == "table":
            if self._depth == 1 and self._rows is not None:
                self.tables.append(self._rows)
                self._rows = None
            self._depth = max(0, self._depth - 1)
            return
        if self._depth != 1:
            return
        if tag == "tr":
            if self._row is not None and self._rows is not None:
                self._rows.append(self._row)
            self._row = None
        elif tag in ("td", "th"):
            if self._cell is not None and self._row is not None:
                self._row.append(self._cell)
            self._cell = None
        elif tag in _BLOCK_TAGS and self._cell is not None:
            self._cell["parts"].append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        if self._cell is not None:
            self._cell["parts"].append(data)


def clean_text(text: str) -> str:
    """Normalise whitespace while keeping meaningful line breaks."""
    text = text.replace("\xa0", " ").replace("​", "")
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n"))
    return re.sub(r"\n{2,}", "\n", "\n".join(lines)).strip()


def _expand(rows: list[list[dict]]) -> list[list[str]]:
    """Expand rowspan/colspan into a dense grid of strings."""
    grid: list[list[str]] = []
    carry: dict[int, tuple[int, str]] = {}  # column -> (rows still to fill, text)

    for row in rows:
        out: list[str] = []
        col = 0
        cells = iter(row)
        while True:
            col = _drain_carry(carry, out, col)
            try:
                cell = next(cells)
            except StopIteration:
                break
            text = clean_text("".join(cell["parts"]))
            for _ in range(cell["colspan"]):
                out.append(text)
                if cell["rowspan"] > 1:
                    carry[col] = (cell["rowspan"] - 1, text)
                col += 1
        _drain_carry(carry, out, col)
        grid.append(out)

    width = max((len(r) for r in grid), default=0)
    for row_out in grid:
        row_out.extend([""] * (width - len(row_out)))
    return grid


def _drain_carry(carry: dict[int, tuple[int, str]], out: list[str], col: int) -> int:
    """Emit any cells carried down from an earlier rowspan, starting at ``col``."""
    while col in carry:
        remaining, text = carry[col]
        out.append(text)
        if remaining > 1:
            carry[col] = (remaining - 1, text)
        else:
            del carry[col]
        col += 1
    return col


def tables_from_html(document: str) -> list[list[list[str]]]:
    """Return every top-level table in ``document`` as a dense grid of strings."""
    collector = _TableCollector()
    collector.feed(document)
    collector.close()
    return [_expand(table) for table in collector.tables]
