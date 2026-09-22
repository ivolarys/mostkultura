"""Pouťová Pecka has explicit programme dates; never infer a new edition."""

from __future__ import annotations

from datetime import date

import pytest

from mostek_kultura.classify import map_native
from mostek_kultura.config import SourceConfig
from mostek_kultura.http import FixtureHttp
from mostek_kultura.normalize import flag_time
from mostek_kultura.sources.poutova_pecka import PoutovaPeckaSource

URL = "https://poutovapecka.cz/"


def test_recorded_fairy_tales_map_to_theatre(root, cfg):
    events = source().fetch(FixtureHttp(root / "tests/fixtures/poutova-pecka"))
    titles = {
        "Jak šel Slávek kolem světa",
        "Kašpárek na skalním hradu",
        "Ruda Hancvencl",
    }
    fairy_tales = {event.title: event for event in events if event.title in titles}
    assert set(fairy_tales) == titles
    assert all(map_native(event.native_category, cfg.category_map) == "divadlo"
               for event in fairy_tales.values())


def source() -> PoutovaPeckaSource:
    return PoutovaPeckaSource(SourceConfig(
        name="poutova-pecka", type="poutova_pecka", url=URL,
        page=f"{URL}#program", place="Pecka",
    ))


def test_recorded_programme_keeps_every_timed_item_and_real_2026_dates(root):
    events = source().fetch(FixtureHttp(root / "tests/fixtures/poutova-pecka"))

    assert len(events) == 16
    assert {event.start.date() for event in events} == {date(2026, 8, 28), date(2026, 8, 29), date(2026, 8, 30)}
    country = events[0]
    assert country.title == "Country kapela Náhoda Pecka"
    assert country.start.isoformat() == "2026-08-28T19:00:00+02:00"
    assert country.native_category == "koncert"
    assert country.venue == "Náměstí Pecka"
    assert country.url == "https://poutovapecka.cz/#program"
    assert country.image == "https://poutovapecka.cz/img/intro_bg_2026.png"
    assert country.native_id == "2026-08-28T19:00:00+02:00|Country kapela Náhoda Pecka"

    puppet = next(event for event in events if event.title == "Kašpárek na skalním hradu")
    assert puppet.start.isoformat() == "2026-08-30T10:30:00+02:00"
    assert puppet.native_category == "divadelní pohádka"
    assert puppet.venue == "Náměstí Pecka"  # Jaroměř belongs to the performers, not the venue.

    fire = next(event for event in events if event.title == "Ohňová show")
    assert fire.venue == "Náměstí Pecka"
    assert fire.native_category == "ohňová show"
    assert len({event.source_id for event in events}) == len(events)

    mass = next(event for event in events if event.title == "Mše svatá")
    assert mass.venue == "Kostel svatého Bartoloměje, Pecka"
    dance = next(event for event in events if event.title == "Hasičská pouťová zábava")
    assert dance.venue == "Před hasičárnou, Pecka"


def test_recorded_past_edition_is_dropped_by_the_shared_time_filter(root):
    events = source().fetch(FixtureHttp(root / "tests/fixtures/poutova-pecka"))
    assert flag_time(events, 60, ref=date(2026, 9, 11)) == []


@pytest.mark.parametrize("heading", [
    "Pátek 28.8.",
    "Pátek 28. srpna 2026",
    "Pátek 31.2.2026",
])
def test_no_year_is_guessed_and_invalid_programme_day_is_rejected(heading):
    html = f"""
    <section id='program'><h3>{heading}</h3>
    <p>19.00 hodin <b>Kapela</b> (koncert)</p></section>
    """
    with pytest.raises(ValueError):
        source().parse(html)


def test_malformed_day_is_not_silently_skipped_beside_a_valid_day():
    html = """
    <section id='program'>
      <h3>Pátek 28.8.</h3><p>19.00 hodin <b>Kapela</b> (koncert)</p>
      <h3>Sobota 29.8.2026</h3><p>20.00 hodin <b>Jiná kapela</b> (koncert)</p>
    </section>
    """
    with pytest.raises(ValueError):
        source().parse(html)


def test_items_with_same_title_but_different_times_have_different_native_ids():
    html = """
    <section id='program'><h3>Sobota 29.8.2026</h3>
    <p>10.00 hodin <b>Kapela</b> (koncert)</p>
    <p>20.00 hodin <b>Kapela</b> (koncert)</p></section>
    """
    events = source().parse(html)
    assert [event.native_category for event in events] == ["koncert", "koncert"]
    assert events[0].native_id != events[1].native_id
