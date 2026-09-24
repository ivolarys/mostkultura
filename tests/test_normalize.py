from datetime import date, datetime

from mostek_kultura.dates import TZ
from mostek_kultura.model import Event
from mostek_kultura.normalize import (
    PlaceResolver,
    dedupe,
    flag_time,
    in_scope,
    norm_title,
    resolve_places,
)


def ev(title, day=12, hour=19, source="a", **kw):
    return Event(title=title, start=datetime(2026, 9, day, hour, tzinfo=TZ), source=source, **kw)


def test_place_aliases(cfg):
    r = PlaceResolver(cfg)
    assert r.resolve("Dvůr Králové n. L.") == "Dvůr Králové nad Labem"
    assert r.resolve("Trutnov – Střední Předměstí") == "Trutnov"
    assert r.resolve("Praha 1") is None
    assert r.resolve("Hrad Pecka - Rytířský sál") == "Pecka"


def test_venue_beats_source_default(cfg):
    r = PlaceResolver(cfg)
    e = ev("První třemešenská burza", venue="Bílá Třemešná", source="dvur-kralove")
    resolve_places([e], r, {"dvur-kralove": "Dvůr Králové nad Labem"})
    assert e.place == "Bílá Třemešná"
    e2 = ev("Koncert", venue="Hankův dům - sál", source="dvur-kralove")
    resolve_places([e2], r, {"dvur-kralove": "Dvůr Králové nad Labem"})
    assert e2.place == "Dvůr Králové nad Labem"


def test_explicit_place_raw_wins_over_title(cfg):
    r = PlaceResolver(cfg)
    e = ev("Trutnovský podzim v Praze", place_raw="Praha 1", venue="Rudolfinum")
    resolve_places([e], r)
    assert e.place is None and not in_scope(e, r)


def test_lodzie_belongs_to_jicin(cfg):
    r = PlaceResolver(cfg)
    e = ev("Koncert", venue="Valdštejnská lodžie", place_raw="Jičín")
    resolve_places([e], r)
    assert e.place == "Jičín" and in_scope(e, r)
    assert e.venue == "Valdštejnská lodžie"
    cached = ev("Koncert", place="Valdštejnská lodžie", place_raw="Valdštejnské imaginárium")
    resolve_places([cached], r)
    assert cached.place == "Jičín" and in_scope(cached, r)


def test_venues_allow(cfg):
    import dataclasses
    cfg2 = dataclasses.replace(cfg, venues_allow=["Sokolovna Horka"])
    r = PlaceResolver(cfg2)
    e = ev("Koncert", venue="Sokolovna Horka", place_raw="Horka u Staré Paky")
    resolve_places([e], r)
    assert e.place is None and in_scope(e, r)


def test_flag_time_and_ongoing():
    ref = date(2026, 9, 11)
    past = ev("stará", day=10)
    today_ev = ev("dnes", day=11)
    exhibition = ev("výstava", day=1, hour=0, end=datetime(2026, 9, 30, tzinfo=TZ), all_day=True)
    two_day = ev("víkendovka", day=12, hour=0, end=datetime(2026, 9, 13, 23, 59, tzinfo=TZ))
    far = Event(title="daleko", start=datetime(2026, 12, 24, tzinfo=TZ), source="a")
    out = flag_time([past, today_ev, exhibition, two_day, far], horizon_days=60, ref=ref)
    titles = [e.title for e in out]
    assert titles == ["dnes", "výstava", "víkendovka"]
    assert exhibition.ongoing and not two_day.ongoing


def test_dedupe_merges_and_prefers_priority():
    a = ev("Koncert: Jaroslav Hutka", source="dvur-kralove", place="Dvůr Králové nad Labem", all_day=True)
    b = ev("Jaroslav Hutka", source="goout", place="Dvůr Králové nad Labem", hour=20,
           image="img", url="https://goout/x")
    out = dedupe([b, a], {"dvur-kralove": 7, "goout": 4})
    assert len(out) == 1
    w = out[0]
    assert w.source == "dvur-kralove" and w.sources == ["goout"]
    assert w.start.hour == 20 and not w.all_day and w.image == "img"
    assert w.urls == ["https://goout/x"]


def test_dedupe_keeps_different_days():
    a = ev("Veřejné bruslení", day=12)
    b = ev("Veřejné bruslení", day=13)
    assert len(dedupe([a, b], {})) == 2


def test_dedupe_keeps_separate_screenings_and_cinemas():
    early = ev("Auta", hour=15, venue="Bio Central", place="Hradec Králové")
    late = ev("Auta", hour=18, venue="Bio Central", place="Hradec Králové")
    cinestar = ev("Auta", hour=15, venue="CineStar Hradec Králové — Sál 1", place="Hradec Králové")
    assert len(dedupe([early, late, cinestar], {})) == 3


def test_dedupe_merges_same_time_same_venue_across_sources():
    a = ev("Auta", source="bio-central", venue="Bio Central — Velký sál", place="Hradec Králové")
    b = ev("Film: Auta", source="goout", venue="Bio Central", place="Hradec Králové")
    out = dedupe([a, b], {"bio-central": 7, "goout": 4})
    assert len(out) == 1 and out[0].sources == ["goout"]


def test_dedupe_ongoing_exhibition_cross_source_year_discrepancy():
    def show(title, year, source, *, place="Hradec Králové", venue="Muzeum východních Čech",
             end_year=2027, ongoing=True, category="vystava"):
        return Event(
            title=title, start=datetime(year, 3, 7, tzinfo=TZ),
            end=datetime(end_year, 12, 31, 23, 59, tzinfo=TZ),
            source=source, place=place, venue=venue, category=category,
            ongoing=ongoing, all_day=True, url=f"https://example.com/{source}/{year}",
        )

    authoritative = show("Velehory v Hradci Králové - MAGICKÝ HIMÁLAJ - výstava", 2025, "muzeum-hk")
    regional = show("Výstava: Velehory v Hradci Králové - MAGICKÝ HIMÁLAJ", 2026,
                    "hradec-vyber", venue="Muzeum východních Čech, Hradec Králové")
    merged = dedupe([regional, authoritative], {"muzeum-hk": 9, "hradec-vyber": 6})
    assert len(merged) == 1
    assert merged[0].source == "muzeum-hk"
    assert merged[0].start.year == 2025 and merged[0].end.year == 2027
    assert merged[0].sources == ["hradec-vyber"]
    assert regional.url in merged[0].urls

    timed_regional = show("Velehory v Hradci Králové - MAGICKÝ HIMÁLAJ", 2026, "hradec-vyber")
    timed_regional.all_day = False
    timed_regional.start = timed_regional.start.replace(hour=14)
    timed_merge = dedupe([show("Velehory v Hradci Králové - MAGICKÝ HIMÁLAJ - výstava",
                               2025, "muzeum-hk"), timed_regional],
                         {"muzeum-hk": 9, "hradec-vyber": 6})
    assert len(timed_merge) == 1
    assert timed_merge[0].start.year == 2025 and timed_merge[0].all_day

    variants = [
        show("Velehory v Hradci Králové - MAGICKÝ HIMÁLAJ druhá část", 2026, "other"),
        show("Velehory v Hradci Králové - MAGICKÝ HIMÁLAJ", 2026, "other", place="Trutnov"),
        show("Velehory v Hradci Králové - MAGICKÝ HIMÁLAJ", 2026, "other", venue="Galerie Artičok"),
        show("Velehory v Hradci Králové - MAGICKÝ HIMÁLAJ", 2026, "other", ongoing=False),
        show("Velehory v Hradci Králové - MAGICKÝ HIMÁLAJ", 2023, "other", end_year=2024),
        show("Velehory v Hradci Králové - MAGICKÝ HIMÁLAJ", 2026, "other", category="koncert"),
        show("Velehory v Hradci Králové - MAGICKÝ HIMÁLAJ", 2026, "muzeum-hk"),
        show("Velehory v Hradci Králové - MAGICKÝ HIMÁLAJ", 2026, "other", venue=None),
    ]
    for candidate in variants:
        assert len(dedupe([show("Velehory v Hradci Králové - MAGICKÝ HIMÁLAJ - výstava",
                                2025, "muzeum-hk"), candidate], {"muzeum-hk": 9})) == 2


def test_norm_title_strips_prefix_and_accents():
    assert norm_title("Koncert: Věra Špinarová!") == "vera spinarova"
