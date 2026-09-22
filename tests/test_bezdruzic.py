"""Bezdružic reads text metadata from current detail pages, never banner names."""

from __future__ import annotations

import pytest

from mostek_kultura.config import SourceConfig
from mostek_kultura.http import FixtureHttp
from mostek_kultura.sources.bezdruzic import BezdruzicSource

HOME = "https://www.bezdruzic.cz/"
FESTIVAL = "https://www.bezdruzic.cz/festival/"
PIVO = "https://www.bezdruzic.cz/pivo"
BOOM = "https://connect.boomevents.org/cs/event/current"


def source() -> BezdruzicSource:
    return BezdruzicSource(SourceConfig(
        name="bezdruzic", type="bezdruzic", url=HOME, place="Pecka",
    ))


class Pages:
    def __init__(self, pages: dict[str, str]):
        self.pages = pages

    def get_text(self, url: str) -> str:
        return self.pages[url]


def homepage(links: str) -> str:
    return f"<section id='akce'><h3>Chystáme pro vás:</h3>{links}<h3>Uplynulé akce:</h3><a href='/festival'>archive</a></section>"


def festival(*, title="PECKA 2026", dates="<h3>pátek 26. června 2026 - od 19.00 hodin</h3>") -> str:
    return f"""
    <header class='intro'><img src='img/header_Pecka_2026.png'></header>
    <section id='program'><p class='intro-text'>Festival na hradě Pecka</p>
    <h1>{title}</h1>{dates}</section>
    """


def boom(*, metadata_row=True, time="20. čvn 2026 (19:21 - 21:21)") -> str:
    row = f'''<div><div><svg class="bi-calendar4-week"></svg></div><div>{time}</div></div>''' if metadata_row else ""
    return '''
    <script>const unrelated = {"start": "1900-01-01T00:00:00Z"};</script>
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"Event","url":"https://connect.boomevents.org/cs/event/current","name":"Marie Rottrová - hrad Pecka","startDate":"20.06.2026","endDate":"20.06.2026","description":"Koncert na nádvoří hradu Pecka.","location":"Hrad Pecka, Pecka, Czechia","image":"https://cdn.example.test/rottrova.jpg"}</script>
    <div><div class="EventDetail-module__stackHeader"><h1>Marie Rottrová - hrad Pecka</h1></div>{row}</div>
    <footer>Doporučená jiná akce: 20. čvn 2026 (10:00 - 12:00)</footer>
    '''.replace("{row}", row)


def test_current_links_use_detail_metadata_and_skip_product_and_archive():
    pages = Pages({
        HOME: homepage(f"<a href='{FESTIVAL}'><img src='banner_2025.jpg'></a><a href='{PIVO}'><img src='pivo.jpg'></a><a href='{BOOM}'><img src='rottrova.jpg'></a>"),
        FESTIVAL: festival(dates="<h3>pátek 26. června 2026 - od 19.00 hodin</h3><h3>sobota 27. června 2026 - od 13.30 hodin</h3>"),
        PIVO: "<h1>KUMRAUS 11°</h1><p>Produkt bez termínu.</p>",
        BOOM: boom(),
    })

    events = source().fetch(pages)

    assert [(event.title, event.start.isoformat()) for event in events] == [
        ("PECKA 2026", "2026-06-26T19:00:00+02:00"),
        ("PECKA 2026", "2026-06-27T13:30:00+02:00"),
        ("Marie Rottrová - hrad Pecka", "2026-06-20T19:21:00+02:00"),
    ]
    assert all(event.place_raw == "Pecka" and event.venue == "Hrad Pecka" for event in events)
    assert events[0].image == "https://www.bezdruzic.cz/festival/img/header_Pecka_2026.png"
    assert events[0].native_category == "festival"
    assert events[-1].end.isoformat() == "2026-06-20T21:21:00+02:00" and not events[-1].all_day


def test_recorded_pages_keep_explicit_2026_festival_and_stale_boom_event(root):
    events = source().fetch(FixtureHttp(root / "tests/fixtures/bezdruzic"))

    festival_events = [event for event in events if event.title == "PECKA 2026"]
    assert [event.start.isoformat() for event in festival_events] == [
        "2026-06-26T19:00:00+02:00", "2026-06-27T13:30:00+02:00",
    ]
    rottrova = next(event for event in events if event.title == "Marie Rottrová - hrad Pecka")
    assert rottrova.start.isoformat() == "2025-06-20T19:21:00+02:00"
    assert rottrova.venue == "Hrad Pecka" and rottrova.place_raw == "Pecka"


@pytest.mark.parametrize("detail", [
    "<section id='program'><h1>PECKA 2026</h1></section>",
    festival(dates="<h3>sobota bez data</h3>"),
])
def test_festival_requires_explicit_title_and_dates(detail):
    pages = Pages({HOME: homepage(f"<a href='{FESTIVAL}'><img src='banner.jpg'></a>"), FESTIVAL: detail})
    with pytest.raises(ValueError):
        source().fetch(pages)


def test_boom_ignores_time_outside_its_metadata_row_and_falls_back_to_all_day():
    events = source().fetch(Pages({HOME: homepage(f"<a href='{BOOM}'>BOOM</a>"), BOOM: boom(metadata_row=False)}))

    event = events[0]
    assert event.start.isoformat() == "2026-06-20T00:00:00+02:00"
    assert event.end.isoformat() == "2026-06-20T23:59:59+02:00" and event.all_day


def test_boom_rejects_metadata_row_that_disagrees_with_event_date():
    pages = Pages({HOME: homepage(f"<a href='{BOOM}'>BOOM</a>"), BOOM: boom(time="21. čvn 2026 (19:21 - 21:21)")})
    with pytest.raises(ValueError, match="disagrees"):
        source().fetch(pages)
