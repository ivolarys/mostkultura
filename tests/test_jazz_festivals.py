"""Festival listings preserve occurrence dates and reject ambiguous editions."""

from datetime import date

import pytest
from bs4 import BeautifulSoup

from mostek_kultura.build import fetch_all
from mostek_kultura.classify import classify
from mostek_kultura.http import FixtureHttp
from mostek_kultura.normalize import PlaceResolver, flag_time, in_scope, resolve_places
from mostek_kultura.sources import make_source


def source(cfg, name):
    return make_source(next(s for s in cfg.sources if s.name == name))


def recorded(cfg, root, name):
    src = source(cfg, name)
    return src, FixtureHttp(root / 'tests' / 'fixtures' / name).get_text(src.cfg.url)


def test_jgtt_recording_dates_venues_and_repeated_title(cfg, root):
    src, html = recorded(cfg, root, 'jgtt')
    events = src.parse(html)
    assert len(events) == 9
    assert [(e.start.strftime('%m-%d %H:%M'), e.venue) for e in events] == [
        ('10-06 19:00', 'Muzeum východních Čech v Hradci Králové'),
        ('10-07 19:00', 'Divadlo Drak'),
        ('10-08 16:00', 'Sauna NUUK'),
        ('10-08 19:00', 'Divadlo Drak'),
        ('10-09 17:00', 'Petrof Gallery'),
        ('10-09 19:00', 'Bio Central'),
        ('10-10 14:00', 'Sauna NUUK'),
        ('10-10 18:00', 'Sbor kněze Ambrože'),
        ('10-10 20:00', 'Bio Central'),
    ]
    assert events[0].title == 'Lenka Gálisová Quartet'
    assert events[0].url == 'https://jgtt.cz/program/lenka-galisova-quartet'
    assert events[0].image.endswith('/402530582_909291647480046_6970133797693075833_n-160x160.jpg')
    repeated = [e for e in events if e.title == 'Prague Quiet Music Collective: 100°C']
    assert len(repeated) == 2 and repeated[0].source_id != repeated[1].source_id
    assert all(e.start.year == 2026 and e.place_raw == 'Hradec Králové' and not e.all_day for e in events)
    assert all(e.image.startswith('https://jgtt.cz/') for e in events)


def test_jazzinec_recording_dates_and_artist_images(cfg, root):
    src, html = recorded(cfg, root, 'jazzinec')
    events = src.parse(html)
    assert [(e.title, e.start.strftime('%Y-%m-%d %H:%M')) for e in events] == [
        ('Tom Skinner', '2026-05-19 19:00'),
        ('Gerald Clark & Jiří Maršíček', '2026-10-10 19:00'),
        ('SORRY, MILES!', '2026-10-22 19:00'),
        ('Lakecia Benjamin', '2026-11-12 19:00'),
        ('Yolk | Filip Żółtowski Quartet', '2026-11-23 19:00'),
    ]
    assert [e.venue for e in events] == ['Síň Bohuslava Martinů'] * 3 + ['UFFO'] + ['Síň Bohuslava Martinů']
    assert events[0].image.endswith('/Tom-Skinner-Voices-of-Bishara.jpg')
    assert events[0].url == 'https://www.jazzinec.cz/Tom-SkinnerVoices-Of-Bishara.html'
    assert all(e.place_raw == 'Trutnov' and not e.all_day and e.image for e in events)
    assert events[-1].start.utcoffset().total_seconds() == 3600


@pytest.mark.parametrize('name', ['jgtt', 'jazzinec'])
def test_festival_dates_and_ids_never_roll_forward(cfg, root, monkeypatch, name):
    src, html = recorded(cfg, root, name)
    before = [(e.source_id, e.start) for e in src.parse(html)]
    monkeypatch.setenv('MOSTEK_NOW', '2030-01-01')
    assert [(e.source_id, e.start) for e in src.parse(html)] == before
    assert len({ident for ident, _ in before}) == len(before)


@pytest.mark.parametrize('name', ['jgtt', 'jazzinec'])
@pytest.mark.parametrize('ambiguous', [False, True])
def test_festival_requires_unambiguous_programme_year(cfg, root, name, ambiguous):
    src, html = recorded(cfg, root, name)
    doc = BeautifulSoup(html, 'html.parser')
    selector = '.marquee__text' if name == 'jgtt' else '#slider img'
    if ambiguous:
        if name == 'jgtt':
            doc.select_one(selector).string = '6.–10. říjen 2027'
        else:
            img = doc.select_one(selector)
            img['src'] = img['src'].replace('2026', '2027')
            img['alt'] = img['alt'].replace('2026', '2027')
    else:
        for tag in doc.select(selector):
            tag.decompose()
    with pytest.raises(ValueError):
        src.parse(str(doc))


@pytest.mark.parametrize('name,empty,card_selector,required', [
    ('jgtt', '<div class="event-list-wrapper"><div class="event-list"></div></div>', 'article.event', '.event__meta-item--time'),
    ('jazzinec', '<div class="program-cont"><div class="container program"></div></div>', '.program-date', '.program-time'),
])
def test_empty_programme_is_valid_but_changed_markup_is_error(cfg, root, name, empty, card_selector, required):
    src, html = recorded(cfg, root, name)
    assert src.parse(empty) == []
    with pytest.raises(ValueError):
        src.parse('<main>Server temporarily unavailable</main>')
    doc = BeautifulSoup(html, 'html.parser')
    doc.select_one(required).decompose()
    with pytest.raises(ValueError):
        src.parse(str(doc))
    doc = BeautifulSoup(html, 'html.parser')
    for tag in doc.select(card_selector):
        tag['class'] = ['changed-markup']
    with pytest.raises(ValueError):
        src.parse(str(doc))


def test_jazzinec_multiple_artists_form_one_concert(cfg, root):
    src, html = recorded(cfg, root, 'jazzinec')
    doc = BeautifulSoup(html, 'html.parser')
    row = doc.select_one('.program-radek')
    extra = BeautifulSoup('<div class="row program-radek"><a href="/other.html">Other Quartet</a><sup>CZ</sup></div>', 'html.parser')
    row.insert_after(extra.div)
    events = src.parse(str(doc))
    assert len(events) == 5
    assert 'Tom Skinner' in events[0].title and 'Other Quartet' in events[0].title
    assert events[0].start.strftime('%Y-%m-%d %H:%M') == '2026-05-19 19:00'


def test_festivals_survive_pipeline_and_expire(cfg, root):
    events, statuses = fetch_all(cfg, root, offline=True, only={'jgtt', 'jazzinec'}, persist=False)
    assert {s.name: (s.status, s.count) for s in statuses} == {'jgtt': ('ok', 9), 'jazzinec': ('ok', 5)}
    resolver = PlaceResolver(cfg)
    resolve_places(events, resolver)
    classify(events, cfg, {}, use_llm=False)
    assert all(e.category == 'koncert' and in_scope(e, resolver) for e in events)
    future = flag_time(events, cfg.horizon_days, ref=date(2026, 10, 12))
    assert [e.title for e in future] == ['SORRY, MILES!', 'Lakecia Benjamin', 'Yolk | Filip Żółtowski Quartet']
    assert flag_time(events, cfg.horizon_days, ref=date(2027, 1, 1)) == []


def test_jazzinec_conflicting_banner_text_and_path_fail(cfg, root):
    src, html = recorded(cfg, root, 'jazzinec')
    doc = BeautifulSoup(html, 'html.parser')
    image = doc.select_one('#slider img')
    image['alt'] = image['alt'].replace('2026', '2027')
    with pytest.raises(ValueError):
        src.parse(str(doc))


def test_jazzinec_partially_missing_date_does_not_silently_drop_concert(cfg, root):
    src, html = recorded(cfg, root, 'jazzinec')
    doc = BeautifulSoup(html, 'html.parser')
    doc.select_one('.program-date').decompose()
    with pytest.raises(ValueError):
        src.parse(str(doc))
