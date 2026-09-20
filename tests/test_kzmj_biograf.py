from mostek_kultura.config import SourceConfig
from mostek_kultura.dates import TZ
from mostek_kultura.http import FixtureHttp
from mostek_kultura.sources.kzmj_biograf import KzmjBiografSource


def _source():
    return KzmjBiografSource(SourceConfig(
        name="biograf-jicin", type="kzmj_biograf", url="https://kzmj.cz/biograf/", place="Jičín",
    ))


def test_kzmj_biograf_fixture_parses_one_responsive_copy(root):
    events = _source().fetch(FixtureHttp(root / "tests" / "fixtures" / "biograf-jicin"))
    assert len(events) == 68
    assert len({event.native_id for event in events}) == len(events)
    basikova = next(event for event in events if event.title == "Bára Basiková")
    assert basikova.start.strftime("%Y-%m-%d %H:%M") == "2026-09-20 17:00"
    assert basikova.start.tzinfo == TZ and basikova.venue == "Biograf Český ráj"
    assert basikova.place_raw == "Jičín" and basikova.native_category == "Film"
    concert = next(event for event in events if event.title == "Petr Kůs a FÁMY")
    assert concert.native_category == "Koncert" and concert.category == "koncert"
    assert concert.url.startswith("https://kzmj.cz/sekce-nefilmova/")
    talkshow = next(event for event in events if event.title.startswith("Talkshow Vítka"))
    assert talkshow.native_category == "Talkshow" and talkshow.category == "prednaska"


def test_kzmj_biograf_keeps_repeated_film_projections_distinct():
    html = """
      <h1>Biograf Český ráj - program</h1>
      <div class='for-small'><div class='list-col-datum'>25.9.2026 pátek 17:00</div>
        <a class='list-col-nazev' href='/sekce-biograf/film/'>Film</a>
        <div class='col-12'><ion-icon name='color-palette-outline'></ion-icon> Drama</div></div>
      <div class='for-small'><div class='list-col-datum'>25.9.2026 pátek 19:30</div>
        <a class='list-col-nazev' href='/sekce-biograf/film/'>Film</a>
        <div class='col-12'><ion-icon name='color-palette-outline'></ion-icon> Drama</div></div>
    """
    events = _source().parse(html)
    assert [event.start.strftime("%H:%M") for event in events] == ["17:00", "19:30"]
    assert len({event.native_id for event in events}) == 2
    assert all(event.native_category == "Film" for event in events)
    assert all(event.category == "film" for event in events)


def test_kzmj_biograf_maps_nonfilm_metadata_to_categories():
    cards = "".join(f"""
      <div class='for-small'><div class='list-col-datum'>25.9.2026 pátek {hour}:00</div>
        <a class='list-col-nazev' href='/sekce-nefilmova/{hour}/'>Test {kind}</a>
        <div class='col-12'><ion-icon name='color-palette-outline'></ion-icon> {kind}</div></div>
    """ for hour, kind in (("17", "Diashow"), ("18", "Talkshow"), ("19", "Stand-Up"), ("20", "Divadlo")))
    events = _source().parse("<h1>Biograf Český ráj - program</h1>" + cards)
    assert [event.category for event in events] == ["prednaska", "prednaska", "divadlo", "divadlo"]


def test_kzmj_biograf_rejects_changed_or_malformed_markup_but_accepts_empty_programme():
    source = _source()
    assert source.parse("<h1>Biograf Český ráj - program</h1>") == []
    try:
        source.parse("<main></main>")
    except ValueError as exc:
        assert "heading" in str(exc)
    else:
        raise AssertionError("changed listing markup must not look like an empty programme")
    changed_responsive_copy = """
      <h1>Biograf Český ráj - program</h1>
      <div class='for-medium'><a class='list-col-nazev' href='/sekce-biograf/test/'>Test</a></div>
    """
    try:
        source.parse(changed_responsive_copy)
    except ValueError as exc:
        assert "responsive" in str(exc)
    else:
        raise AssertionError("missing small copy must not look like an empty programme")
    malformed = """
      <h1>Biograf Český ráj - program</h1>
      <div class='for-small'><div class='list-col-datum'>25.9.2026 pátek 17:00</div>
        <a class='list-col-nazev' href='/sekce-nefilmova/test/'>Test</a></div>
    """
    try:
        source.parse(malformed)
    except ValueError as exc:
        assert "malformed" in str(exc)
    else:
        raise AssertionError("malformed event card must fail the source")
