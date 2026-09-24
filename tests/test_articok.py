"""Artičok dates come from post titles, never from publication or body times."""

from copy import deepcopy
from datetime import date

import pytest

from mostek_kultura.build import fetch_all
from mostek_kultura.http import FixtureHttp
from mostek_kultura.normalize import PlaceResolver, dedupe, flag_time, resolve_places
from mostek_kultura.sources import make_source


def source(cfg):
    return make_source(next(s for s in cfg.sources if s.name == "articok-hk"))


def post(title, *, identifier=1, published="2026-08-27T09:00:00", content=""):
    return {
        "id": identifier, "date": published, "categories": [1],
        "title": {"rendered": title}, "content": {"rendered": content},
        "link": f"https://www.articok.cz/post-{identifier}/", "_embedded": {},
    }


class JsonHttp:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    def get_json(self, url):
        self.urls.append(url)
        return self.pages[len(self.urls) - 1]


def test_recorded_posts_have_expected_dates_categories_and_venues(cfg, root):
    events = source(cfg).fetch(FixtureHttp(root / "tests/fixtures/articok-hk"))
    assert len(events) == 4
    by_id = {e.native_id.split("|")[0]: e for e in events}
    assert set(by_id) == {"10455", "10439", "10429", "10420"}
    assert by_id["10455"].title == "Zlatovláska"
    assert by_id["10455"].start.isoformat() == "2026-09-13T16:00:00+02:00"
    assert by_id["10455"].end is None
    assert by_id["10439"].start.isoformat() == "2026-11-13T16:00:00+01:00"
    assert by_id["10439"].end.isoformat() == "2026-11-13T22:00:00+01:00"
    assert by_id["10439"].venue == "Vinotéka IN VINO"
    assert by_id["10429"].start.isoformat() == "2026-10-07T18:30:00+02:00"
    assert by_id["10429"].native_category == "Přednáška"
    assert by_id["10429"].venue == "Galerie Artičok"
    assert by_id["10420"].start.isoformat() == "2026-09-12T10:00:00+02:00"
    assert by_id["10420"].end.isoformat() == "2026-09-12T15:00:00+02:00"
    assert all(e.url.startswith("https://www.articok.cz/") and e.image and len(e.description) <= 500
               for e in events)
    assert len({e.source_id for e in events}) == len(events)


def test_publication_year_is_fixed_and_body_times_are_ignored(cfg, monkeypatch):
    items = [
        post("Večer 13.9. 17.30", content="<p>Prodej od 12:00, program do 22:00.</p>"),
        post("Výstava 13. listopadu 2027", identifier=2),
        post("Nový rok 2.ledna 18:00", identifier=3, published="2026-12-20T10:00:00"),
        post("Vernisáž 4.října", identifier=4),
        post("Bez termínu", identifier=5, content="Koná se 13.9. v 16:00"),
        post("Chybný den 32.9. 18:00", identifier=6),
        post("17. ročník festivalu 13.9. 19:00", identifier=7),
        post("Koncert v 18.30", identifier=8),
        post("Nesmysl 13.13. 18:00", identifier=9),
        post("Nesmysl 13.19. 18:00", identifier=10),
    ]
    events = source(cfg).parse(items)
    assert len(events) == 5
    assert events[0].start.isoformat() == "2026-09-13T17:30:00+02:00"
    assert events[0].end is None
    assert events[1].start.year == 2027 and events[1].all_day
    assert events[2].start.isoformat() == "2027-01-02T18:00:00+01:00"
    assert events[3].start.year == 2026 and events[3].all_day
    assert events[4].title == "17. ročník festivalu"
    monkeypatch.setenv("MOSTEK_NOW", "2028-09-24")
    assert [e.start for e in source(cfg).parse(items)] == [e.start for e in events]
    assert not flag_time(events, cfg.horizon_days, ref=date(2028, 9, 24))


def test_date_ranges_and_explicit_venue_in_full_body(cfg):
    long_body = "<p>" + "informace " * 90 + "</p><p>Akce je před Vinotéku IN VINO.</p>"
    items = [
        post("Výstava 16.3 – 20.3.2027", content=long_body),
        post("Novoroční akce 31.12 – 2.1. 10 – 15 hodin", identifier=2,
             published="2026-12-01T09:00:00"),
    ]
    events = source(cfg).parse(items)
    assert events[0].start.isoformat() == "2027-03-16T00:00:00+01:00"
    assert events[0].end.isoformat() == "2027-03-20T23:59:00+01:00"
    assert events[0].venue == "Vinotéka IN VINO"
    assert events[1].start.isoformat() == "2026-12-31T10:00:00+01:00"
    assert events[1].end.isoformat() == "2027-01-02T15:00:00+01:00"


@pytest.mark.parametrize("title,expected_end", [
    ("Festival 16.3.–20.3.2027 17:00", "2027-03-20T23:59:00+01:00"),
    ("Festival 16.3.–31.2.2027 17:00", None),
    ("Festival 20.3.–16.3.2027 17:00", None),
])
def test_single_time_date_range_has_valid_end(cfg, title, expected_end):
    events = source(cfg).parse([post(title)])
    if expected_end is None:
        assert events == []
    else:
        assert len(events) == 1
        assert events[0].start.isoformat() == "2027-03-16T17:00:00+01:00"
        assert events[0].end.isoformat() == expected_end


def test_empty_and_broken_api_and_pagination(cfg):
    src = source(cfg)
    assert src.fetch(JsonHttp([[]])) == []
    for broken in ({"message": "error"}, [None]):
        with pytest.raises(ValueError):
            src.fetch(JsonHttp([broken]))
    first = [post("Večer 13.9. 18:00") for _ in range(100)]
    second = [post("Další den 14.9. 18:00", identifier=2)]
    client = JsonHttp([first, second])
    assert len(src.fetch(client)) == 2
    assert client.urls[0].endswith("&offset=0")
    assert client.urls[1].endswith("&offset=100")
    with pytest.raises(ValueError, match="page limit"):
        src.fetch(JsonHttp([deepcopy(first) for _ in range(5)]))


def test_havelka_merges_with_hkinfo(root, cfg):
    events, statuses = fetch_all(cfg, root, offline=True,
                                 only={"articok-hk", "hradec-vyber"}, persist=False)
    assert all(s.status == "ok" for s in statuses)
    resolve_places(events, PlaceResolver(cfg), {s.name: s.place for s in cfg.sources})
    havelka = [e for e in events if "HAVELK" in e.title.upper()]
    assert {e.source for e in havelka} == {"articok-hk", "hradec-vyber"}
    merged = dedupe(havelka, {s.name: s.priority for s in cfg.sources})
    assert len(merged) == 1
    assert merged[0].source == "articok-hk"
    assert merged[0].sources == ["hradec-vyber"]
