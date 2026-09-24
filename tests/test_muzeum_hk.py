"""Museum JEvents calendar, recorded details and source overlap."""

from datetime import date

import pytest

from mostek_kultura.http import FixtureHttp
from mostek_kultura.normalize import PlaceResolver, dedupe, resolve_places
from mostek_kultura.sources import make_source


def source(cfg, name="muzeum-hk"):
    return make_source(next(s for s in cfg.sources if s.name == name))


def test_recorded_months_and_details(cfg, root):
    src = source(cfg)
    assert src.month_urls(date(2026, 12, 31)) == [
        "https://www.muzeumhk.cz/program/kalendar-akci/udalostimesice/2026/12/-.html",
        "https://www.muzeumhk.cz/program/kalendar-akci/udalostimesice/2027/1/-.html",
        "https://www.muzeumhk.cz/program/kalendar-akci/udalostimesice/2027/2/-.html",
    ]
    events = src.fetch(FixtureHttp(root / "tests/fixtures/muzeum-hk"))
    assert len(events) == 35
    assert len({event.native_id for event in events}) == len(events)
    by_id = {event.native_id: event for event in events}
    assert "677" not in by_id  # A synthetic multi-year permanent display.
    assert "1686" not in by_id and "1699" not in by_id  # School-only sessions.
    assert "1640" in by_id  # The professional workshop also admits other participants.
    assert by_id["1669"].start.isoformat() == "2026-09-25T17:00:00+02:00"
    assert by_id["1669"].end.isoformat() == "2026-09-25T22:00:00+02:00"
    assert by_id["1685"].start.isoformat() == "2026-09-25T17:30:00+02:00"
    assert by_id["1662"].venue == "Hlavní odborné pracoviště Gayerova kasárna"
    assert by_id["1666"].venue == "Muzeum východních Čech - budova ARCHA"
    assert by_id["1676"].start.isoformat() == "2026-10-06T19:00:00+02:00"
    assert by_id["1308"].start.isoformat() == "2025-03-07T10:00:00+01:00"
    assert by_id["1308"].end.isoformat() == "2026-11-29T18:00:00+01:00"
    assert by_id["1308"].native_category == "Výstava"
    assert by_id["1679"].native_category == "Přednáška"
    assert by_id["1659"].place_raw == "Chlum"
    assert by_id["1659"].venue == "Muzeum války 1866"


def test_valid_empty_month_and_broken_markup(cfg):
    src = source(cfg)
    url = src.month_urls(date(2026, 9, 24))[0]
    assert src.parse_month("<div id='jevents_body'><div class='cal_table'></div></div>", url) == {}
    for html in ("", "<main></main>", "<div id='jevents_body'></div>"):
        with pytest.raises(ValueError, match="markup missing"):
            src.parse_month(html, url)
    malformed = "<div id='jevents_body'><div class='cal_table'><a class='cal_titlelink' href='/wrong'>Event</a></div></div>"
    with pytest.raises(ValueError, match="malformed event link"):
        src.parse_month(malformed, url)


def test_dates_are_explicit_and_images_ignore_placeholders(cfg):
    src = source(cfg)
    start, end, all_day = src.parse_summary("Od pátek, 3. prosinec 2021 - 10:00 Do čtvrtek, 31. prosinec 2026 - 18:00")
    assert start.isoformat() == "2021-12-03T10:00:00+01:00"
    assert end.isoformat() == "2026-12-31T18:00:00+01:00"
    assert not all_day
    for raw in ("pátek, 25. září", "v říjnu", "pátek, 32. září 2026"):
        with pytest.raises(ValueError):
            src.parse_summary(raw)
    html = """<div id='jevents_body'><h1 class='jev_evdt_title'>Nová výstava</h1>
      <div class='jev_evdt_summary'>pátek, 25. září 2026, 17:00 - 22:00</div>
      <div class='jev_evdt_desc'><img src='data:image/svg+xml;base64,PHN2' data-src='/images/exhibit.jpg'>Popis</div>
      <div class='jev_evdt_location'>Místo<br>Muzeum test<br>Hlavní 1<br>Brno</div></div>"""
    event = src.parse_detail(html, "https://www.muzeumhk.cz/event", "1", "Výstavy")
    assert event.image == "https://www.muzeumhk.cz/images/exhibit.jpg"
    assert event.place_raw == "Brno" and event.venue == "Muzeum test"
    with pytest.raises(ValueError, match="detail markup missing"):
        src.parse_detail("<main></main>", "https://www.muzeumhk.cz/event", "1")


def test_archa_overlap_prefers_direct_museum(cfg, root):
    direct = source(cfg).fetch(FixtureHttp(root / "tests/fixtures/muzeum-hk"))
    regional = source(cfg, "hradec-vyber").fetch(FixtureHttp(root / "tests/fixtures/hradec-vyber"))
    events = [event for event in direct + regional
              if event.start.date() == date(2026, 9, 30)
              and event.start.hour == 17
              and "prohlídka nové budovy" in event.title.casefold()]
    assert len(events) == 2
    resolve_places(events, PlaceResolver(cfg), {s.name: s.place for s in cfg.sources})
    merged = dedupe(events, {s.name: s.priority for s in cfg.sources})
    assert len(merged) == 1
    assert merged[0].source == "muzeum-hk"
    assert merged[0].sources == ["hradec-vyber"]
