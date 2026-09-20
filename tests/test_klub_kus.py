"""Klub Kus parser behaviour independent of its recorded live fixture."""

from __future__ import annotations

import pytest

from mostek_kultura.config import SourceConfig
from mostek_kultura.http import FixtureHttp
from mostek_kultura.sources.klub_kus import KlubKusSource


def source() -> KlubKusSource:
    return KlubKusSource(SourceConfig(
        name="klub-kus", type="klub_kus", url="https://www.kulturaturnov.cz/klub-kus", place="Turnov",
    ))


def listing(cards: str) -> str:
    return f"<main><div id='programList'><div class='program-list _blue'>{cards}</div></div></main>"


def card(*, date="2026-10-03 20:00:00", title="Bratři Orffové", href="program/kus/bratri-orffove",
         description="Oceňovaná česká alternativní kapela.") -> str:
    return f"""
    <article><div><time datetime='{date}'>20:00</time></div>
    <div><img src='data/photogallery/orffove.jpg'></div><div><h2>{title}</h2>
    <p class='event_note'>Básníci ticha</p><p>{description}</p><a href='{href}'></a></div></article>
    """


def test_klub_kus_reads_local_datetime_venue_description_image_and_link():
    event = source().parse(listing(card()))[0]

    assert event.title == "Bratři Orffové"
    assert event.start.isoformat() == "2026-10-03T20:00:00+02:00"
    assert event.place_raw == "Turnov" and event.venue == "Klub Kus"
    assert event.url == "https://www.kulturaturnov.cz/program/kus/bratri-orffove"
    assert event.image == "https://www.kulturaturnov.cz/data/photogallery/orffove.jpg"
    assert event.description == "Oceňovaná česká alternativní kapela."
    assert event.native_category is None


def test_klub_kus_recording_keeps_future_items_and_winter_offset(cfg, root):
    cfg_source = next(item for item in cfg.sources if item.name == "klub-kus")
    events = KlubKusSource(cfg_source).fetch(FixtureHttp(root / "tests/fixtures/klub-kus"))

    assert len(events) == 9
    beata = next(event for event in events if event.title == "Beata Hlavenková & Monodie 2.0")
    assert beata.start.isoformat() == "2026-11-13T20:00:00+01:00"
    assert beata.venue == "Klub Kus" and beata.place_raw == "Turnov"
    assert beata.image == "https://www.kulturaturnov.cz/data/photogallery/bh_anezkahorova2021_thumb_38853.png"
    assert beata.native_category is None


def test_klub_kus_keeps_repeated_detail_url_at_different_times_as_distinct_events():
    events = source().parse(listing(card(date="2026-10-03 18:00:00") + card(date="2026-10-03 20:00:00")))

    assert len(events) == 2
    assert events[0].url == events[1].url
    assert events[0].source_id != events[1].source_id


def test_klub_kus_accepts_valid_empty_listing():
    assert source().parse(listing("")) == []


@pytest.mark.parametrize("html", [
    "<main></main>",
    listing("<article><h2>Bez času</h2><a href='program/kus/x'></a></article>"),
    listing(card(date="2026-10-03")),
    listing(card(date="není datum")),
])
def test_klub_kus_rejects_broken_programme_markup(html):
    with pytest.raises(ValueError):
        source().parse(html)
