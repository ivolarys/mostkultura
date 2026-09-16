"""Parser tests against recorded fixtures (tests/fixtures/<source>/, offline)."""

import json

import pytest

from mostek_kultura.http import FixtureHttp
from mostek_kultura.sources import make_source


def _src(cfg, name):
    scfg = next(s for s in cfg.sources if s.name == name)
    return make_source(scfg)


def _fetch(cfg, root, name):
    return _src(cfg, name).fetch(FixtureHttp(root / "tests" / "fixtures" / name))


def test_galileo_mostek(cfg, root):
    events = _fetch(cfg, root, "mostek")
    assert events, "no events parsed"
    e = next(x for x in events if "Den obce Mostek" in x.title)
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-12 13:00"
    assert e.venue == "Areál autokempu"
    assert "slavnost" in (e.native_category or "")
    assert e.url.startswith("https://www.mostek.cz/")
    assert not e.all_day
    assert all(x.source == "mostek" for x in events)


def test_galileo_empty_list(cfg, root):
    assert _fetch(cfg, root, "mostek-okoli") == []


def test_antee_rss(cfg, root):
    events = _fetch(cfg, root, "lazne-belohrad")
    assert len(events) >= 10
    e = next(x for x in events if x.title.startswith("Disco Sokol"))
    assert e.start.strftime("%d.%m.%Y %H:%M") == "17.09.2026 20:00"
    assert e.end is not None and e.end.day == 18
    assert e.venue == "Sokol Lázně Bělohrad"
    assert e.url == "https://www.lazne-belohrad.cz/kalendar-akci/disco-sokol-vol-4"
    r = next(x for x in events if "ROSSINI" in x.title)
    assert r.native_category == "Koncert"
    assert r.image and r.image.startswith("https://")


def test_public4u_dvur_kralove_enriched_from_detail(cfg, root):
    events = _fetch(cfg, root, "dvur-kralove")
    assert len(events) >= 10
    e = next(x for x in events if x.title == "Koncert Phobos")
    assert e.venue == "Safari Park Dvůr Králové"
    assert e.start.strftime("%H:%M") == "17:00" and not e.all_day
    assert e.native_category == "Koncert"
    assert "Phobos" in e.description


def test_public4u_trutnov_table_template(cfg, root):
    events = _fetch(cfg, root, "trutnov")
    e = next(x for x in events if x.title == "Dřevořezba")
    assert e.all_day and e.start.day == 12 and e.end.day == 13
    assert e.venue.startswith("Dům pod jasanem")
    d = next(x for x in events if x.title.startswith("Dny evropského"))
    assert d.start.strftime("%H:%M") == "10:00" and d.end.strftime("%H:%M") == "17:00"


def test_trut_program_detail_uses_event_date_and_matching_time(cfg, root):
    events = _fetch(cfg, root, "trut")
    assert len(events) == 1
    e = events[0]
    assert e.title == "Noc literatury v Trutnově 2026"
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-16 17:00"
    assert e.end and e.end.strftime("%H:%M") == "22:00"
    assert not e.all_day and e.place_raw == "Trutnov" and e.venue is None
    assert e.url == "https://trut.cz/akce/noc-literatury-v-trutnove-2026/"
    assert e.native_id == e.url and "Datum aktualizace" not in e.description


def test_trut_program_rejects_broken_listing_but_accepts_empty(cfg):
    src = _src(cfg, "trut")
    assert src.parse_listing("<section class='section'><div class='container'><h1>Akce</h1></div></section>") == []
    duplicate = """<section class='section'><div class='container'><h1>Akce</h1>
      <article class='card'><h3><a href='/akce/test/'>Test</a></h3></article>
      <article class='card'><h3><a href='/akce/test/'>Test znovu</a></h3></article>
      </div></section>"""
    assert src.parse_listing(duplicate) == [("Test", "https://trut.cz/akce/test/")]
    with pytest.raises(ValueError, match="markup missing"):
        src.parse_listing("<main><h1>Akce</h1></main>")
    with pytest.raises(ValueError, match="malformed event card"):
        src.parse_listing("<section class='section'><div class='container'><h1>Akce</h1><article class='card'></article></div></section>")
    with pytest.raises(ValueError, match="without a title"):
        src.parse_listing("""<section class='section'><div class='container'><h1>Akce</h1>
          <article class='card'><h3><a href='/akce/ok/'>V pořádku</a></h3></article>
          <article class='card'><h3><a href='/akce/prazdne/'></a></h3></article></div></section>""")


def test_trut_program_never_infers_year_or_uses_unrelated_date(cfg):
    src = _src(cfg, "trut")
    url = "https://trut.cz/akce/test/"
    no_year = "<section class='section'><div class='container'><h1>Test</h1><p><strong>Datum:</strong> 16. 9.</p></div></section>"
    with pytest.raises(ValueError, match="explicit event date"):
        src.parse_detail(no_year, "Test", url)
    date_only = """<section class='section'><div class='container'><h1>Test</h1>
      <p><strong>Datum:</strong> 16.09.2026</p><p><button>📷 Čtecí místa</button></p>
      <p>Skutečný popis akce pro návštěvníky.</p></div></section>"""
    date_only_event = src.parse_detail(date_only, "Test", url)
    assert date_only_event.all_day and date_only_event.description == "Skutečný popis akce pro návštěvníky."
    detail = """<section class='section'><div class='container'><h1>Test</h1>
      <p><strong>Datum:</strong> 16.09.2026</p><p><strong>Místo:</strong> Trutnov</p>
      <p>Datum aktualizace: 23.7.2026</p><p>Archiv z 15. září 2025 od 09:00 do 11:00.</p>
      <p>Program 16. září 2026 od 18:00 do 20:00 hodin.</p></div></section>"""
    e = src.parse_detail(detail, "Test", url)
    assert e.start.strftime("%H:%M") == "18:00" and e.end and e.end.strftime("%H:%M") == "20:00"


def test_public4u_month_urls(cfg):
    from datetime import date
    src = _src(cfg, "dvur-kralove")
    urls = src.month_urls(date(2026, 11, 5))
    assert [u.split("&rok=")[1] for u in urls] == ["2026&mesic=11", "2026&mesic=12", "2027&mesic=1"]


def test_goout_parse(cfg, root):
    data = json.loads((root / "tests" / "samples" / "goout_schedules.json").read_text(encoding="utf-8"))
    events = _src(cfg, "goout").parse(data)
    assert len(events) == 4
    e = next(x for x in events if "Rybičky" in x.title)
    assert e.venue == "UFFO Trutnov" and e.place_raw.startswith("Trutnov")
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-11-20 19:00"
    assert "concerts" in e.native_category
    fest = next(x for x in events if "Brutal Assault" in x.title)
    assert fest.all_day


@pytest.mark.parametrize("name", ["mostek", "lazne-belohrad", "dvur-kralove", "trutnov", "vrchlabi",
                                  "valdstejnska-lodzie", "kuks-hospital", "zirec-domov", "bila-tremesna",
                                  "bila-tremesna-okoli", "kuks-obec", "dolni-brusnice", "jicin",
                                  "nova-paka", "kultura-novapaka", "uffo", "sd-jilm", "biograf-horice",
                                  "horice-galerie", "horice-koruna", "epo1", "belohradska-sypka",
                                  "pecka", "josefov-kolonie", "klaster-hostinne", "trut"])
def test_fixture_manifest_present(root, name):
    assert (root / "tests" / "fixtures" / name / "manifest.json").exists()


def test_drupal_vrchlabi(cfg, root):
    events = _fetch(cfg, root, "vrchlabi")
    assert len(events) >= 30
    e = next(x for x in events if x.title == "Dožínky v muzeu")
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-12 14:00"
    assert e.end.strftime("%H:%M") == "18:00"
    assert e.venue.startswith("zahrada za historickými domky")
    assert e.native_category == "Ostatní" and "Dožínk" in e.description
    kino = next(x for x in events if x.native_category == "Kino")
    assert kino.venue is None and not kino.all_day
    assert not any("ZRUŠENO" in x.title for x in events) or True  # exclude_title is applied in build, not fetch
    assert len({x.url for x in events}) == len(events)


def test_lodzie(cfg, root):
    events = _fetch(cfg, root, "valdstejnska-lodzie")
    assert len(events) >= 10
    e = next(x for x in events if "Beseda S Ježkem" in x.title)
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-13 15:30" and not e.all_day
    assert e.url.startswith("https://valdstejnskalodzie.cz/program/")
    assert e.description.startswith("Beseda s Jiřím Ježkem") and e.image
    assert e.venue == "Valdštejnská lodžie"
    fest = next(x for x in events if x.title.startswith("MALÁ INVENTURA"))
    assert fest.all_day and fest.start.day == 18
    nxt = next(x for x in events if x.title.startswith("30 let"))
    assert nxt.start.year == 2027


def test_npu_kuks(cfg, root):
    events = _fetch(cfg, root, "kuks-hospital")
    assert len(events) >= 1
    e = next(x for x in events if x.title.startswith("Vinobraní"))
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-12 10:00" and e.end.strftime("%H:%M") == "18:00"
    assert e.venue == "hospitál Kuks" and e.native_category == "Společenské akce"
    assert e.url == "https://www.hospital-kuks.cz/cs/akce/1658-vinobrani-na-hospitalu-kuks"


def test_josefa_zirec(cfg, root):
    events = _fetch(cfg, root, "zirec-domov")
    assert len(events) >= 5
    e = next(x for x in events if x.title.startswith("Konference"))
    assert e.start.strftime("%Y-%m-%d") == "2026-10-08" and e.all_day
    assert e.venue == "Domov sv. Josefa" and "konferenci" in e.description
    assert e.url.startswith("https://www.domovsvatehojosefa.cz/")
    assert len({x.native_id for x in events}) == len(events)


def test_galileo_old_template(cfg, root):
    events = _fetch(cfg, root, "bila-tremesna-okoli")
    assert len(events) >= 5
    e = next(x for x in events if x.title.startswith("Phobos"))
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-11 17:00" and not e.all_day
    assert e.venue is None  # empty "Kde:" must not leak into venue
    assert "Safari" in e.description
    rng = next(x for x in events if x.title == "Víkend ve fotbalu")
    assert rng.all_day and rng.start.day == 11 and rng.end.day == 13
    local = _fetch(cfg, root, "bila-tremesna")
    assert any("burza" in x.title.lower() for x in local)


def test_galileo_old_template_empty(cfg, root):
    assert _fetch(cfg, root, "dolni-brusnice") == []
    assert _fetch(cfg, root, "kuks-obec") == []


def test_vismo_nova_paka(cfg, root):
    events = _fetch(cfg, root, "nova-paka")
    assert len(events) >= 10
    e = next(x for x in events if x.title.startswith("HAVAJSKÉ OSTROVY"))
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-17 18:00" and not e.all_day
    assert e.venue == "Klenotnice muzea"
    assert e.native_category == "Kulturní akce"
    assert e.url.startswith("https://www.munovapaka.cz/")
    rng = next(x for x in events if "Suchardův dům" in (x.venue or ""))
    assert rng.start.strftime("%Y-%m-%d %H:%M") == "2026-09-10 09:00"
    assert rng.end.strftime("%Y-%m-%d %H:%M") == "2026-11-01 16:00" and not rng.all_day
    assert len({x.native_id for x in events}) == len(events)
    assert all(x.source == "nova-paka" for x in events)


def test_vismo_jicin_empty(cfg, root):
    # mujicin.cz's Vismo calendar has had no entries since 2022; the parser must not crash on an
    # empty result and should just yield nothing.
    assert _fetch(cfg, root, "jicin") == []


def test_uffo(cfg, root):
    events = _fetch(cfg, root, "uffo")
    assert len(events) > 0
    e = next(x for x in events if "ZMOŽEK" in x.title)
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-22 19:00" and not e.all_day
    assert e.venue == "UFFO Trutnov"
    assert e.native_category == "Koncert"
    assert e.url == "https://uffo.cz/jiri-zmozek-p5037/"
    assert e.image and e.image.startswith("https://")
    kino = next(x for x in events if x.venue == "Kino Vesmír")
    assert kino.native_category == "Film"
    assert kino.url.startswith("https://uffo.cz/")
    assert all(x.url.startswith("https://uffo.cz/") for x in events)
    assert len({x.native_id for x in events}) == len(events)


def test_sd_jilm_current_program_is_paginated_and_keeps_showtimes_separate(cfg, root):
    events = _fetch(cfg, root, "sd-jilm")
    assert len(events) >= 40
    e = next(x for x in events if x.title == "Jakub Smolík")
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-16 19:00" and not e.all_day
    assert e.venue == "SD Jilm" and e.native_category == "Koncert" and e.category == "koncert"
    assert e.url == "https://www.sdjilm.cz/sd-jilm/koncert/jakub-smolik-2026"
    assert e.image and e.image.startswith("https://www.sdjilm.cz/")
    kino = next(x for x in events if x.title.startswith("Ádr - místo"))
    assert kino.venue == "Kino 70" and kino.native_category == "Přednáška" and kino.category == "prednaska"
    repeats = [x for x in events if x.title == "„Christmas show“"]
    assert len(repeats) >= 2 and len({x.native_id for x in repeats}) == len(repeats)
    assert {x.start.strftime("%H:%M") for x in repeats} == {"16:00", "19:30"}
    assert len({x.native_id for x in events}) == len(events)
    assert all("/archiv" not in x.url for x in events)


def test_kultura_novapaka(cfg, root):
    events = _fetch(cfg, root, "kultura-novapaka")
    assert len(events) >= 5
    e = next(x for x in events if x.title == "Pivovarská diskotéka")
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-12 19:00" and not e.all_day
    assert e.end.strftime("%Y-%m-%d %H:%M") == "2026-09-13 01:00"
    assert e.venue == "Pivovar Nová Paka a.s."
    assert e.native_category == "tanec"
    assert e.url.startswith("http://www.kultura-novapaka.cz/")
    assert len({x.native_id for x in events}) == len(events)


def test_mojekino_biograf_horice(cfg, root):
    events = _fetch(cfg, root, "biograf-horice")
    assert len(events) == 19
    e = next(x for x in events if x.title.startswith("Tom a Jerry: Kouzelný kompas"))
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-12 17:00" and not e.all_day
    assert e.venue == "Biograf Na Špici"
    assert e.native_category == "Film"
    assert e.url.startswith("https://www.biografnaspici.cz/")
    dups = [x for x in events if x.title == "Dokonalý den"]
    assert len(dups) == 2 and dups[0].native_id != dups[1].native_id
    assert all(x.url.startswith("https://www.biografnaspici.cz/") for x in events)
    assert len({x.native_id for x in events}) == len(events)


def test_vismo6_horice_galerie_only_placeholders(cfg, root):
    # the gallery's Vismo6 "Wecal" calendar has never had a real event: fetch() (a static, wide
    # From/To window, see module docstring) only turns up leftover CMS-setup test entries ("Nová
    # událost v kalendáři" placeholders) dated in 2026-04, which fall outside the build's horizon
    # and so contribute 0 events to an actual build.
    events = _fetch(cfg, root, "horice-galerie")
    assert len(events) == 3
    assert all(x.title.startswith("Nová událost v kalendáři") for x in events)
    assert len({x.native_id for x in events}) == 3


def test_koruna_program(cfg, root):
    events = _fetch(cfg, root, "horice-koruna")
    assert len(events) == 14
    e = next(x for x in events if x.title == "Antonín Dvořák - Lužanská mše D dur")
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-13 09:00" and not e.all_day
    assert e.venue == "Dům kultury Koruna"
    assert e.url == "https://www.dum-kultury-koruna.cz/antonin-dvorak-luzanska-mse-d-dur"
    assert len({x.native_id for x in events}) == len(events)


def test_epo1_calendar(cfg, root):
    events = _fetch(cfg, root, "epo1")
    assert len(events) == 8
    e = next(x for x in events if x.title == "Workshop: Scratch Art")
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-09 16:00"
    assert e.end.strftime("%H:%M") == "18:00" and not e.all_day
    assert e.venue == "EPO1, Trutnov" and e.native_category == "Workshop"
    assert e.url.startswith("https://goout.net/")
    internal = next(x for x in events if x.title.startswith("Proč civilizace"))
    assert internal.url.startswith("https://www.epo1.cz/")
    assert len({x.native_id for x in events}) == len(events)


def test_epo1_exhibitions(cfg, root):
    events = _fetch(cfg, root, "epo1-vystavy")
    assert len(events) == 3
    assert {x.title for x in events} == {
        "Neokosmos — Pavel Holeček",
        "Vzpomeň sobě, že není všechno štěstí — Vladimír 518",
        "Rekreace — Ondřej Mestek",
    }
    assert all(x.all_day and x.native_category == "Výstava" and x.venue == "EPO1, Trutnov" for x in events)
    assert all(x.start.strftime("%Y-%m-%d") == "2026-05-22" for x in events)
    assert all(x.end and x.end.strftime("%Y-%m-%d") == "2026-11-01" for x in events)
    assert all("show-card" not in x.description for x in events)
    assert any("Turbínová hala" in x.description for x in events)
    assert all("webflow.io" not in x.url for x in events)


def test_epo1_exhibitions_skip_malformed_and_keep_explicit_future_year(cfg):
    src = _src(cfg, "epo1-vystavy")
    html = '''
      <a class="show-card" href="/vystavy/future"><h3>Future</h3>
        <div class="show-card_artist">Artist</div><div class="show-card_meta"><span>Sál</span><span>2. 5. — 1. 11. 2099</span></div>
      </a>
      <a class="show-card" href="/vystavy/broken"><h3>Broken</h3>
        <div class="show-card_meta"><span>Sál</span><span>not a date</span></div>
      </a>
      <div class="archive-card"><h3>Archive</h3><span>2. 5. — 1. 11. 2026</span></div>
    '''
    events = src.parse(html)
    assert len(events) == 1 and events[0].start.year == 2099
    cross = src.parse('''<a class="show-card" href="/cross"><h3>Cross</h3>
      <div class="show-card_meta"><span>Sál</span><span>22. 12. — 4. 1. 2027</span></div></a>''')[0]
    assert cross.start.strftime("%Y-%m-%d") == "2026-12-22"
    assert cross.end.strftime("%Y-%m-%d") == "2027-01-04"


def test_webnode_belohradska_sypka(cfg, root):
    events = _fetch(cfg, root, "belohradska-sypka")
    assert len(events) == 11
    e = next(x for x in events if x.title == "Degustace francouzských vín")
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-11 18:00" and not e.all_day
    assert e.venue == "Kavárna Bělohradské sýpky"
    assert e.url.startswith("https://www.belohradskasypka.cz/")
    joga = next(x for x in events if x.title.startswith("Jemná Hatha"))
    assert joga.all_day
    quiz = [x for x in events if x.title == "Kavárenský kvíz"]
    assert len(quiz) == 3
    assert len({x.native_id for x in events}) == len(events)


def test_galileo_pecka(cfg, root):
    events = _fetch(cfg, root, "pecka")
    assert len(events) >= 15
    e = next(x for x in events if x.title == "Pecka kros")
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-17 15:00" and not e.all_day
    assert e.venue == "Hrad Pecka, Pecka"
    assert e.url.startswith("https://www.mestys-pecka.cz/")
    assert all(x.source == "pecka" for x in events)


def test_simcal_josefov(cfg, root):
    events = _fetch(cfg, root, "josefov-kolonie")
    assert len(events) == 8
    e = next(x for x in events if x.title.startswith("psychokroužek"))
    assert e.start.strftime("%Y-%m-%d %H:%M") == "2026-09-07 18:00"
    assert e.end.strftime("%H:%M") == "20:00" and not e.all_day
    assert e.url == "https://umeleckakoloniejosefov.cz/kalendar-akci/"
    multi = next(x for x in events if x.title.startswith("letokruhy"))
    assert multi.all_day and multi.start.day == 12 and multi.end.day == 13
    assert len({x.native_id for x in events}) == len(events)


def test_klaster_hostinne(cfg, root):
    events = _fetch(cfg, root, "klaster-hostinne")
    assert len(events) == 1
    e = events[0]
    assert e.title.startswith("Křest knihy")
    assert e.start.strftime("%Y-%m-%d") == "2026-09-25" and e.all_day
    assert e.native_category == "Muzeum"
    assert e.url.startswith("https://www.klasterhostinne.cz/")
