"""Tests for the arbeidsplan scraper.

The fixtures mirror the real document's quirks: merged cells spanning several
time rows, the "Uke: NN" marker living inside a table cell, a whole-week
holiday note, stacked notes in one overview cell, and a blank week template.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from schoolplan import diff, fetch, render_html, render_ics, render_md  # noqa: E402
from schoolplan.dates import date_for, parse_times, school_year_start, year_for_week  # noqa: E402
from schoolplan.highlights import classify, split_homework  # noqa: E402
from schoolplan.parse import parse_document  # noqa: E402
from schoolplan.tablegrid import tables_from_html  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
TODAY = dt.date(2026, 9, 18)  # a Friday in week 38


@pytest.fixture(scope="module")
def plan():
    document = (FIXTURES / "arbeidsplan_8e.html").read_text(encoding="utf-8")
    return parse_document(document, "8E", source_url="https://example.invalid/pub",
                          term_start_year=2026, today=TODAY)


# ----------------------------------------------------------------- table grid

def test_rowspan_and_colspan_expand_to_a_dense_grid():
    grids = tables_from_html(
        "<table><tr><td rowspan='2'>A</td><td>B</td></tr><tr><td>C</td></tr></table>"
    )
    assert grids == [[["A", "B"], ["A", "C"]]]


def test_colspan_repeats_across_columns():
    grids = tables_from_html("<table><tr><td colspan='3'>X</td></tr></table>")
    assert grids[0][0] == ["X", "X", "X"]


def test_script_content_is_not_treated_as_cell_text():
    grids = tables_from_html("<table><tr><td>ok<script>var x=1;</script></td></tr></table>")
    assert grids[0][0][0] == "ok"


# ---------------------------------------------------------------------- dates

def test_school_year_starts_in_august():
    assert school_year_start(dt.date(2026, 9, 18)) == 2026
    assert school_year_start(dt.date(2027, 5, 4)) == 2026


def test_autumn_weeks_stay_in_the_start_year_and_spring_weeks_roll_over():
    assert year_for_week(38, 2026) == 2026
    assert year_for_week(2, 2026) == 2027


def test_week_and_weekday_resolve_to_a_real_date():
    assert date_for(38, "Mandag", 2026) == dt.date(2026, 9, 14)
    assert date_for(38, "Fredag", 2026) == dt.date(2026, 9, 18)


def test_unknown_weekday_is_rejected():
    assert date_for(38, "Blursday", 2026) is None


@pytest.mark.parametrize(
    "label,expected",
    [
        ("08.30 - 09.00", ("08:30", "09:00")),
        ("09:40-10:10", ("09:40", "10:10")),
        ("11:40.12:10", ("11:40", "12:10")),   # typo in the real document
        ("storefri", (None, None)),
        ("", (None, None)),
    ],
)
def test_time_slot_labels_are_parsed_despite_inconsistent_separators(label, expected):
    assert parse_times(label) == expected


# ----------------------------------------------------------------- classifying

@pytest.mark.parametrize(
    "text,category",
    [
        ("Nasjonal prøve i lesing", "test"),
        ("Planleggingsdag", "dayoff"),
        ("Høstferie", "dayoff"),
        ("Foreldremøte", "meeting"),
        ("Klassetur til Bergen museum", "trip"),
        ("HUSK LADER", "bring"),
    ],
)
def test_norwegian_keywords_map_to_categories(text, category):
    assert category in classify(text)


def test_an_ordinary_lesson_is_not_flagged():
    assert classify("Matematikk. Tema: negative tall") == []


def test_homework_lines_are_split_out_of_the_lesson_body():
    homework, detail = split_homework(
        ["Tema: negative tall.", "Lekse: oppgaveboken s. 16 og 17."]
    )
    assert homework == ["oppgaveboken s. 16 og 17."]
    assert detail == ["Tema: negative tall."]


def test_a_wrapped_homework_line_keeps_its_continuation():
    homework, _ = split_homework(["Lekse: les kapittel 3", "og gjør oppgave 4"])
    assert homework == ["les kapittel 3 og gjør oppgave 4"]


# --------------------------------------------------------------------- parsing

def test_only_weeks_with_a_number_are_parsed(plan):
    assert [w.week for w in plan.weeks] == [38]  # the blank template is skipped


def test_week_dates_are_resolved(plan):
    week = plan.weeks[0]
    assert (week.monday, week.friday) == ("2026-09-14", "2026-09-18")


def test_weekly_messages_and_teachers_are_captured(plan):
    week = plan.weeks[0]
    assert week.messages == [
        "Presentasjoner i engelsk på fredag",
        "Nasjonale prøver i lesing på tirsdag",
    ]
    assert week.teachers == "Kristin Norang, Rune Thomassen"


def test_day_columns_carry_the_school_day_span(plan):
    monday = plan.weeks[0].days[0]
    assert (monday.name, monday.starts, monday.ends) == ("Mandag", "08:30", "15:00")


def test_a_merged_cell_becomes_one_lesson_spanning_both_slots(plan):
    monday = plan.weeks[0].days[0]
    assert len(monday.lessons) == 1
    lesson = monday.lessons[0]
    assert (lesson.subject, lesson.start, lesson.end) == ("Naturfag", "09:40", "10:40")


def test_homework_is_attached_to_the_lesson_it_belongs_to(plan):
    thursday = next(d for d in plan.weeks[0].days if d.name == "Torsdag")
    lesson = thursday.lessons[0]
    assert lesson.subject == "Matematikk"
    assert lesson.homework == ["oppgaveboken s. 16 og 17."]
    assert "homework" in lesson.tags
    assert "Lekse" not in lesson.detail


def test_lessons_are_dated(plan):
    friday = next(d for d in plan.weeks[0].days if d.name == "Fredag")
    assert all(lesson.date == "2026-09-18" for lesson in friday.lessons)


# ------------------------------------------------------------- oversiktsplan

def test_a_whole_week_note_is_marked_as_such(plan):
    holiday = next(t for t in plan.term if "Høstferie" in t.text)
    assert holiday.day is None
    assert holiday.date == "2026-10-05"
    assert holiday.tags == ["dayoff"]


def test_stacked_notes_in_one_cell_become_separate_entries(plan):
    friday_38 = [t for t in plan.term if t.week == 38 and t.day == "Fredag"]
    assert {t.text for t in friday_38} == {
        "Presentasjon i engelsk",
        "Nasjonal prøve i matematikk",
    }


def test_punctuation_only_cells_are_ignored(plan):
    assert all(t.text != "!" for t in plan.term)


# ------------------------------------------------------------------ highlights

def test_homework_produces_a_highlight(plan):
    homework = [h for h in plan.highlights if h.category == "homework"]
    assert any("oppgaveboken" in h.title for h in homework)
    assert all(h.date for h in homework)


def test_a_plain_lesson_produces_no_highlight(plan):
    assert not any(h.title == "Naturfag" and h.category == "test" for h in plan.highlights)


def test_highlights_are_sorted_by_date(plan):
    dates = [h.date for h in plan.highlights if h.date]
    assert dates == sorted(dates)


def test_highlights_are_deduplicated(plan):
    keys = [(h.date, h.start, h.category, h.title.lower()) for h in plan.highlights]
    assert len(keys) == len(set(keys))


# --------------------------------------------------------------------- output

def test_ics_is_wellformed_and_folded(plan):
    text = render_ics.render(plan)
    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.rstrip().endswith("END:VCALENDAR")
    assert text.count("BEGIN:VEVENT") == text.count("END:VEVENT") > 0
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))


def test_ics_uids_are_stable_across_runs(plan):
    assert render_ics.render(plan).count("UID:") == render_ics.render(plan).count("UID:")
    first = [l for l in render_ics.render(plan).split("\r\n") if l.startswith("UID:")]
    second = [l for l in render_ics.render(plan).split("\r\n") if l.startswith("UID:")]
    assert first == second and len(set(first)) == len(first)


def test_ics_escapes_separators():
    assert render_ics.escape("a,b;c\nd") == "a\\,b\\;c\\nd"


def test_ics_can_be_filtered_to_one_category(plan):
    text = render_ics.render(plan, categories=("homework",))
    assert text.count("BEGIN:VEVENT") == len(
        [h for h in plan.highlights if h.category == "homework" and h.date]
    )


def test_homework_events_carry_a_reminder(plan):
    assert "BEGIN:VALARM" in render_ics.render(plan, categories=("homework",))


def test_html_is_self_contained_and_escaped(plan):
    page = render_html.render(plan, today=TODAY)
    assert page.startswith("<!doctype html>")
    assert "<script" not in page.lower()
    assert "Uke 38" in page


def test_markdown_digest_lists_this_weeks_homework(plan):
    text = render_md.render(plan, today=TODAY)
    assert "## Uke 38" in text
    assert "oppgaveboken" in text


# ----------------------------------------------------------------------- diff

def test_first_run_reports_no_changes(plan):
    assert diff.compare(None, plan)["first_run"] is True


def test_identical_scrapes_produce_no_changes(plan):
    changes = diff.compare(plan, plan)
    assert changes["added"] == [] and changes["removed"] == []


def test_an_edited_plan_is_reported_as_added_and_removed():
    original = (FIXTURES / "arbeidsplan_8e.html").read_text(encoding="utf-8")
    old = parse_document(original, "8E", term_start_year=2026, today=TODAY)
    new = parse_document(original.replace("Fotografering", "Foreldremøte"),
                         "8E", term_start_year=2026, today=TODAY)
    changes = diff.compare(old, new)
    assert [c["title"] for c in changes["added"]] == ["Foreldremøte"]
    assert [c["title"] for c in changes["removed"]] == ["Fotografering"]


def test_change_summary_is_human_readable():
    assert render_md.summarise_changes({"added": [1], "removed": []}) == "1 nye"
    assert render_md.summarise_changes({"first_run": True}) == "første kjøring"


# ---------------------------------------------------------------------- index

def test_class_links_are_read_from_the_index_page():
    links = fetch.class_links((FIXTURES / "index.html").read_text(encoding="utf-8"))
    assert links["8E"] == "https://docs.google.com/document/d/e/EEE/pub"
    assert set(links) == {"8A", "8E", "10C"}


@pytest.mark.parametrize("raw,expected", [("8 e", "8E"), ("8E", "8E"), ("10c", "10C"),
                                          ("Arbeidsplaner", None), ("", None)])
def test_class_labels_are_normalised(raw, expected):
    assert fetch.normalise_class(raw) == expected


def test_json_roundtrips(plan):
    from schoolplan.model import Plan

    restored = Plan.from_dict(plan.to_dict())
    assert restored.to_dict() == plan.to_dict()


# ------------------------------------------------------- auxiliary homework tables

def test_day_keyed_homework_cell_is_parsed():
    """Rothaugen keeps homework in one cell using "Til <dag>:" as day headings."""
    from schoolplan import aux

    cell = ("Til tirsdag:\nTil onsdag:\nTil torsdag:\n"
            "Matte: Jobb vidare med algebraheftet.\nTil fredag:\nNaturfag: Hugs rapporten.")
    items = aux.day_keyed_homework(cell, "t")
    assert [(h.day, h.subject) for h in items] == [
        ("Torsdag", "Matte"), ("Fredag", "Naturfag")
    ]


def test_day_keyed_homework_is_found_inside_a_grid():
    """Regression: the headings are line-anchored, so the whole cell never matches."""
    from schoolplan import aux

    grid = [["Hjemmearbeid", "Beskjeder"],
            ["Til torsdag:\nMatte: side 12", "Husk gymtøy"]]
    assert [h.subject for h in aux.find_homework(grid, {}, "t")] == ["Matte"]


def test_subject_table_homework_is_parsed():
    """Kirkevoll uses a "Fag | Forberedelser til timen" table."""
    from schoolplan import aux

    grid = [["Fag:", "Forberedelser til timen:", "Tema", "Frister"],
            ["Spansk", "Pugg endelsene på AR-verb", "Verbet Ser", ""],
            ["Tysk", "Lær presens, side 229", "", ""]]
    assert [(h.subject, h.text) for h in aux.find_homework(grid, {}, "t")] == [
        ("Spansk", "Pugg endelsene på AR-verb"), ("Tysk", "Lær presens, side 229")
    ]


def test_lekser_row_in_a_timetable_is_parsed():
    """Slåtthaug puts a LEKSER: row inside the timetable, one cell per day."""
    from schoolplan import aux

    grid = [["LEKSER:", "Naturfag: Les s. 20", "KRLE: øv på prøven"]]
    items = aux.lekser_row_homework(grid, {1: "Mandag", 2: "Tirsdag"}, "t")
    assert [(h.day, h.subject) for h in items] == [("Mandag", "Naturfag"), ("Tirsdag", "KRLE")]


def test_messages_are_pulled_from_a_noticeboard_cell():
    from schoolplan import aux

    assert aux.messages([["Oppslagstavle: Kroppsøving: Møt under taket."]]) == [
        "Kroppsøving: Møt under taket."
    ]


# ---------------------------------------------------------------- bergen sources

def test_school_name_falls_back_to_the_slug():
    from schoolplan import bergen

    assert bergen.school_name("gimle-oppveksttun-skole") == "Gimle oppveksttun skole"


def test_school_name_prefers_the_link_back_to_the_school():
    """The slug is ASCII, so only the page gives "Alvøen" rather than "Alvoen"."""
    from schoolplan import bergen

    page = '<a href="/omkommunen/avdelinger/alvoen-skole">Alvøen skole</a>'
    assert bergen._page_title(page, "alvoen-skole") == "Alvøen skole"


def test_pdf_entries_take_their_label_from_the_anchor_attributes():
    """The CMS writes the visible text with JS; the title is in data-tittel."""
    from schoolplan import bergen

    page = ('<h2>5.trinn</h2><a class="file-link" href="/api/rest/filer/V123" '
            'data-tittel="Ukeplan - uke 39" data-type="pdf">x</a>')
    entries = bergen._entries_on_page("nordnes-skole", "u", page)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.kind == bergen.PDF
    assert entry.label == "5.trinn – Ukeplan - uke 39"
    assert (entry.trinn, entry.week) == (5, 39)


def test_gdocs_entries_are_read_with_their_class():
    from schoolplan import bergen

    page = '<a href="https://docs.google.com/document/d/e/X/pub">8E</a>'
    entries = bergen._entries_on_page("gimle-oppveksttun-skole", "u", page)
    assert (entries[0].kind, entries[0].klasse, entries[0].slug) == (bergen.GDOCS, "8E", "8e")


def test_week_labels_are_not_mistaken_for_classes():
    from schoolplan import bergen

    assert bergen._label_facts("Uke 38") == (None, None, 38)


def test_label_block_homework_ignores_time_slots_and_headings():
    """Regression: scanning a whole column swept the timetable's times in as homework."""
    from schoolplan import aux

    grid = [["Lekser:", "Matematikk: gjør oppgave 1.124 til 1.126"],
            ["8.15 - 9:15", "Norsk"],
            ["9.25-10:25", "Engelsk"]]
    items = aux.label_block_homework(grid, "t")
    assert [h.subject for h in items] == ["Matematikk"]


@pytest.mark.parametrize("line", [
    "8.15 - 9:15", "Til tirsdag", "Til onsdag:", "Arbeidsplan fransk 8.trinn",
    "Lekseplan i tysk", "kort",
])
def test_lines_that_only_look_like_homework_are_rejected(line):
    from schoolplan import aux

    assert not aux._is_real_homework(line)


def test_real_homework_lines_are_kept():
    from schoolplan import aux

    assert aux._is_real_homework("Matematikk: oppgaveboken s. 16 og 17")
    assert aux._is_real_homework("Les tilbakemeldingen du har fått")


# ------------------------------------------------------ dates in the day header

@pytest.mark.parametrize("text,expected", [
    ("Mandag 21.9", dt.date(2026, 9, 21)),
    ("Tirsdag 22/9", dt.date(2026, 9, 22)),
    ("Onsdag 23.09.26", dt.date(2026, 9, 23)),
    ("Mandag 30. september", dt.date(2026, 9, 30)),
    ("Torsdag 1. oktober", dt.date(2026, 10, 1)),
])
def test_explicit_dates_in_a_day_header_are_read(text, expected):
    from schoolplan.dates import date_in_day_header

    assert date_in_day_header(text, 2026) == expected


@pytest.mark.parametrize("text", ["Mandag\n08.30-15.00", "11.10", "Mandag", "08.30 - 09.00"])
def test_times_are_never_mistaken_for_dates(text):
    """"11.10" is as likely a time as a date; only a weekday name settles it."""
    from schoolplan.dates import date_in_day_header

    assert date_in_day_header(text, 2026) is None


def test_a_dated_day_header_sets_the_week_without_guessing():
    doc = """<table>
      <tr><td></td><td>Mandag 21.9</td><td>Tirsdag 22.9</td><td>Onsdag 23.9</td></tr>
      <tr><td>09:00-10:00</td><td>Matematikk<br>Lekse: side 12</td><td></td><td></td></tr>
    </table>"""
    parsed = parse_document(doc, "8E", term_start_year=2026, today=TODAY)
    week = parsed.weeks[0]
    assert week.inferred_week is False      # derived from a real date, not guessed
    assert week.week == 39
    assert [d.date for d in week.days] == ["2026-09-21", "2026-09-22", "2026-09-23"]
    assert any(h.category == "homework" and h.date == "2026-09-21" for h in parsed.highlights)


def test_a_dated_header_still_reads_the_school_day_hours():
    doc = """<table>
      <tr><td></td><td>Mandag 21.9<br>08.30-15.00</td><td>Tirsdag 22.9<br>09.40-14.30</td>
          <td>Onsdag 23.9<br>08.30-13.20</td></tr>
      <tr><td>09:00-10:00</td><td>Norsk</td><td>Norsk</td><td>Norsk</td></tr>
    </table>"""
    week = parse_document(doc, "8E", term_start_year=2026, today=TODAY).weeks[0]
    assert (week.days[0].starts, week.days[0].ends) == ("08:30", "15:00")


def test_a_stated_week_is_not_marked_inferred(plan):
    assert [w.inferred_week for w in plan.weeks] == [False]


def test_a_guessed_week_produces_no_dated_highlights():
    """A timetable with no "Uke: NN" must not emit calendar entries on guessed dates."""
    doc = """<table>
      <tr><td></td><td>Mandag</td><td>Tirsdag</td><td>Onsdag</td><td>Torsdag</td><td>Fredag</td></tr>
      <tr><td>09:00-10:00</td><td>Matematikk<br>Lekse: side 12</td><td></td><td></td><td></td><td></td></tr>
    </table>"""
    parsed = parse_document(doc, "8E", term_start_year=2026, today=TODAY)
    assert parsed.weeks and parsed.weeks[0].inferred_week is True
    assert parsed.weeks[0].days[0].lessons  # the timetable is still available
    assert parsed.highlights == []          # but nothing is put in the calendar


def test_a_stated_week_wins_over_an_inferred_duplicate():
    """Schools pre-fill coming weeks with the timetable and no "Uke: NN" yet."""
    table = """<table>
      <tr><td colspan="3">Arbeidsplan for 8E<br>Uke: 38</td></tr>
      <tr><td></td><td>Mandag</td><td>Tirsdag</td><td>Onsdag</td><td>Torsdag</td><td>Fredag</td></tr>
      <tr><td>09:00-10:00</td><td>Matematikk<br>Lekse: side 12</td><td></td><td></td><td></td><td></td></tr>
    </table>"""
    blank = """<table>
      <tr><td></td><td>Mandag</td><td>Tirsdag</td><td>Onsdag</td><td>Torsdag</td><td>Fredag</td></tr>
      <tr><td>09:00-10:00</td><td>Matematikk</td><td></td><td></td><td></td><td></td></tr>
    </table>"""
    parsed = parse_document(table + blank, "8E", term_start_year=2026, today=TODAY)
    assert [(w.week, w.inferred_week) for w in parsed.weeks] == [(38, False)]
