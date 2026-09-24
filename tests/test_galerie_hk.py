"""GMU's monthly AJAX calendar and dated exhibition listings."""

import json

import pytest

from mostek_kultura.http import FixtureHttp
from mostek_kultura.normalize import PlaceResolver, dedupe, resolve_places
from mostek_kultura.sources import make_source


def source(cfg, name="galerie-hk"):
    return make_source(next(s for s in cfg.sources if s.name == name))


def test_recorded_calendar_and_exhibitions(cfg, root):
    events = source(cfg).fetch(FixtureHttp(root / "tests/fixtures/galerie-hk"))
    assert len(events) == 36
    by_title = {e.title: e for e in events}
    dj = by_title["Summer closing DJ set | LickMySoul"]
    assert dj.start.isoformat() == "2026-09-25T18:00:00+02:00"
    assert dj.end.isoformat() == "2026-09-25T22:00:00+02:00"
    assert dj.native_category == "Koncert" and "terase" in dj.description.lower()
    assert by_title["Workshop figurální kresby"].start.year == 2026
    assert by_title["Workshop figurální kresby"].native_category == "Workshop"
    atelier = sorted((e for e in events if e.title == "Hrateliér | Se dřevem"), key=lambda e: e.start)
    assert [e.start.strftime("%H:%M") for e in atelier] == ["10:00", "15:00"]
    assert all(e.end is None and e.native_category == "Workshop" for e in atelier)
    exhibit = by_title["Dar Vladimíra Preclíka Královéhradeckému kraji"]
    assert exhibit.start.isoformat() == "2025-05-23T00:00:00+02:00"
    assert exhibit.end.date().isoformat() == "2027-01-31"
    assert exhibit.native_category == "Výstava" and exhibit.all_day
    assert "České umění 20. století a jeho škatulky" not in by_title
    assert "Archwerk.cz | Corral" not in by_title
    assert all(e.venue == "Galerie moderního umění v Hradci Králové" for e in events)
    assert len({e.source_id for e in events}) == len(events)


def test_calendar_empty_bad_payload_and_explicit_month(cfg):
    src = source(cfg)
    assert src.parse_calendar('""', year=2026, month=9) == []
    assert src.parse_calendar(json.dumps("<h3>Pro tento měsíc není žádný program.</h3>"), year=2026, month=9) == []
    for bad in ("", "{", "{}", '"<p>Broken</p>"', '"<div class=\\"program-item\\"></div>"'):
        with pytest.raises(ValueError):
            src.parse_calendar(bad, year=2026, month=9)
    card = """<div class='program-item'><div><span class='date-label'>PÁ 25/09</span></div>
        <div><span>18:00–22:00 | Akce</span></div><div><h3><a href='/nepravidelne-akce/'>Koncert</a></h3>
        <p>Prodej od 12:00 a další program v 23:00.</p></div></div>"""
    event = src.parse_calendar(json.dumps(card), year=2026, month=9)[0]
    assert event.start.hour == 18 and event.end.hour == 22
    with pytest.raises(ValueError, match="month"):
        src.parse_calendar(json.dumps(card), year=2026, month=10)
    assert src.parse_calendar(json.dumps(card), year=2027, month=9)[0].start.year == 2027


def test_exhibition_ranges_need_valid_explicit_years(cfg):
    src = source(cfg)
    def card(text):
        return f"<section class='vystavy'><div><h2>Prostor</h2><h3 class='inherit-h2'><a href='/vystavy/test/'>{text}</a></h3></div></section>"
    with pytest.raises(ValueError, match="markup missing"):
        src.parse_exhibitions("<main></main>")
    assert src.parse_exhibitions(card("Název 24/04–01/11")) == []
    assert src.parse_exhibitions(card("Název 24/04/26–01/11/25")) == []
    assert src.parse_exhibitions(card("Název 31/02/26–01/11/26")) == []
    event = src.parse_exhibitions(card("Název 24/04/24–01/11/26"))[0]
    assert event.start.year == 2024 and event.end.year == 2026
    assert src.parse_exhibitions(card("Název 24/04/24–01/11/26").replace("Prostor", "Stálá expozice")) == []


def test_hkinfo_duplicate_uses_direct_source(cfg, root):
    direct = source(cfg).fetch(FixtureHttp(root / "tests/fixtures/galerie-hk"))
    regional = source(cfg, "hradec-vyber").fetch(FixtureHttp(root / "tests/fixtures/hradec-vyber"))
    events = [e for e in direct + regional if "SUMMER CLOSING" in e.title.upper()]
    assert len(events) == 2
    resolve_places(events, PlaceResolver(cfg), {s.name: s.place for s in cfg.sources})
    merged = dedupe(events, {s.name: s.priority for s in cfg.sources})
    assert len(merged) == 1
    assert merged[0].source == "galerie-hk"
    assert merged[0].sources == ["hradec-vyber"]

    direct_slots = [e for e in direct if e.title == "Hrateliér | Se dřevem"]
    regional_slots = [e for e in regional if e.title.startswith("HRATELIÉR | Se dřevem")]
    slots = direct_slots + regional_slots
    resolve_places(slots, PlaceResolver(cfg), {s.name: s.place for s in cfg.sources})
    merged_slots = dedupe(slots, {s.name: s.priority for s in cfg.sources})
    assert len(merged_slots) == 2
    assert {e.start.hour for e in merged_slots} == {10, 15}
