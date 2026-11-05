"""Public observatory schedules keep authoritative dates and exclude private bookings."""

from datetime import date
from urllib.parse import urljoin

import pytest
from bs4 import BeautifulSoup

from mostek_kultura.http import FixtureHttp
from mostek_kultura.normalize import flag_time
from mostek_kultura.sources import make_source


def source(cfg, name):
    return make_source(next(s for s in cfg.sources if s.name == name))


def hk_pages(cfg, root):
    src = source(cfg, 'astrohk')
    http = FixtureHttp(root / 'tests/fixtures/astrohk')
    return src, http.get_text(src.cfg.url), http.get_text(urljoin(src.cfg.url, 'mesicnik.php'))


def test_astrohk_recorded_month_and_programme(cfg, root):
    src, html, month = hk_pages(cfg, root)
    events = src.parse(html, month)
    assert len(events) == 38
    assert all(e.start.year == 2026 and e.start.month == 11 for e in events)
    assert all(e.venue == 'Hvězdárna a planetárium v Hradci Králové' for e in events)
    living = [e for e in events if 'Living Worlds' in e.title]
    assert [e.start.day for e in living] == [4, 11, 18, 25]
    assert all(e.start.strftime('%H:%M') == '18:30' and e.end.strftime('%H:%M') == '20:00' for e in living)
    vietnam = next(e for e in events if e.title == 'Jak žijí lidé v horách Vietnamu')
    assert vietnam.start.isoformat() == '2026-11-12T18:00:00+01:00'
    assert vietnam.category == 'prednaska' and 'Zdeněk Porkert' in vietnam.description
    kids = [e for e in events if e.category == 'deti']
    assert len(kids) == 8
    observations = [e for e in events if 'pozorování' in e.title.lower()]
    assert len(observations) == 16
    assert all('pouze za jasné oblohy' in e.description.lower() for e in observations)
    assert len({e.source_id for e in events}) == 38


def test_astrohk_requires_consistent_explicit_edition(cfg, root, monkeypatch):
    src, html, month = hk_pages(cfg, root)
    expected = [(e.source_id, e.start) for e in src.parse(html, month)]
    monkeypatch.setenv('MOSTEK_NOW', '2030-02-01')
    assert [(e.source_id, e.start) for e in src.parse(html, month)] == expected
    with pytest.raises(ValueError):
        src.parse(html, month.replace('Mesicnik-2026-11.pdf', 'Mesicnik-2027-11.pdf'))
    with pytest.raises(ValueError):
        src.parse(html.replace('Program na listopad', 'Program na prosinec'), month)
    with pytest.raises(ValueError):
        src.parse(html, '<footer>Copyright 2026</footer>')


def test_astrohk_changed_markup_is_not_empty_programme(cfg, root):
    src, html, month = hk_pages(cfg, root)
    assert src.parse('<div id="vse"></div>', '') == []
    with pytest.raises(ValueError):
        src.parse('<main>Service unavailable</main>', month)
    doc = BeautifulSoup(html, 'html.parser')
    for button in doc.select('#vse button.faq'):
        button['class'] = ['changed']
    with pytest.raises(ValueError):
        src.parse(str(doc), month)


def synthetic_hk(group='STŘEDY', item='18:30 | Test', month='říjen', year=2026, number=10):
    html = f'<b>Program na {month}</b><div id="vse"><table><tr><td>{group}</td></tr></table><button class="faq">{item}</button><div class="odpoved"><table><tr><td>Test description</td></tr></table></div></div>'
    issue = f'<a href="data/mesicnik/{year}/Mesicnik-{year}-{number:02}.pdf">AKTUÁLNÍ ČÍSLO - {month} {year}</a>'
    return html, issue


def test_astrohk_explicit_weekday_restrictions(cfg):
    src = source(cfg, 'astrohk')
    assert [e.start.day for e in src.parse(*synthetic_hk(item='18:30 | Test | pouze 28. 10.'))] == [28]
    assert [e.start.day for e in src.parse(*synthetic_hk(group='STŘEDY kromě 28. 10.'))] == [7, 14, 21]
    with pytest.raises(ValueError):
        src.parse(*synthetic_hk(item='18:30 | Test | dle domluvy'))
    assert src.parse(*synthetic_hk(item='18:30 | Test | pouze 28. 10. 2025')) == []


def test_astrohk_quizzes_are_explicit_public_events(cfg):
    events = source(cfg, 'astrohk').parse(*synthetic_hk(group='KVÍZY', item='29. 10. 18:00 | Vesmírný kvíz'))
    assert len(events) == 1
    assert events[0].start.isoformat() == '2026-10-29T18:00:00+01:00'
    with pytest.raises(ValueError):
        source(cfg, 'astrohk').parse(*synthetic_hk(group='NOVÝ VEŘEJNÝ PROGRAM', item='29. 10. 18:00 | Test'))


def ics_event(title='Přednáška', start='DTSTART:20261113T180000Z', end='DTEND:20261113T200000Z', extra='', uid='one'):
    return f'BEGIN:VEVENT\nUID:{uid}\nSUMMARY:{title}\n{start}\n{end}\n{extra}\nEND:VEVENT\n'


def calendar(*events):
    return 'BEGIN:VCALENDAR\nVERSION:2.0\n' + ''.join(events) + 'END:VCALENDAR\n'


def test_jicin_real_calendar_has_two_current_public_events(cfg, root, monkeypatch):
    monkeypatch.setenv('MOSTEK_NOW', '2026-11-03')
    src = source(cfg, 'hvezdarna-jicin')
    events = src.fetch(FixtureHttp(root / 'tests/fixtures/hvezdarna-jicin'))
    current = sorted(flag_time(events, 60, ref=date(2026, 11, 3)), key=lambda e: e.start)
    assert len(current) == 2
    assert [e.start.isoformat() for e in current] == ['2026-11-06T19:00:00+01:00', '2026-11-13T19:00:00+01:00']
    assert all(e.end.strftime('%H:%M') == '21:00' and e.venue == 'Hvězdárna Jičín' for e in current)
    assert 'Saturnu a Jesliček' in current[0].title
    assert 'ISS' in current[1].title
    assert current[1].url == 'https://www.hvezdarnajicin.cz/iss-nas-druhy-domov-ve-vesmiru/'
    assert current[1].image and current[1].image.startswith('https://www.hvezdarnajicin.cz/')
    assert len({e.source_id for e in current}) == 2


@pytest.mark.parametrize('title', ['Úklid', 'Vánoční prázdniny', 'Školní přednáška', 'Soukromé pozorování', 'Pronájem – přednáška', 'Porada', 'Astronomický kroužek', 'ZRUŠENO přednáška'])
def test_jicin_excludes_nonpublic_and_cancelled_titles(cfg, title):
    assert source(cfg, 'hvezdarna-jicin').parse_ics(calendar(ics_event(title))) == []


def test_jicin_ics_dates_places_and_stability(cfg, monkeypatch):
    src = source(cfg, 'hvezdarna-jicin')
    text = calendar(
        ics_event('Vesmírný kvízník - venkovní hra', 'DTSTART;VALUE=DATE:20261028', 'DTEND;VALUE=DATE:20261102', uid='game'),
        ics_event('Přednáška', extra='LOCATION:Knihovna Jičín', uid='offsite'),
        ics_event('Prázdninové pozorování', uid='holiday-program'),
    )
    events = src.parse_ics(text)
    assert len(events) == 3
    assert events[0].all_day and events[0].end.date() == date(2026, 11, 1)
    assert events[0].venue is None
    assert events[1].venue == 'Knihovna Jičín'
    before = [(e.source_id, e.start) for e in events]
    monkeypatch.setenv('MOSTEK_NOW', '2030-01-01')
    assert [(e.source_id, e.start) for e in src.parse_ics(text)] == before
    assert src.parse_ics(calendar(ics_event(extra='STATUS:CANCELLED'))) == []
    assert src.parse_ics(calendar()) == []
    with pytest.raises(ValueError):
        src.parse_ics('<html>Server error</html>')
    with pytest.raises(ValueError):
        src.parse_ics(calendar(ics_event(start='DTSTART:invalid')))


def upice_pages(cfg, root):
    from mostek_kultura.sources.upice_observations import _API, _HOURS
    src = source(cfg, 'hvezdarna-upice')
    http = FixtureHttp(root / 'tests/fixtures/hvezdarna-upice')
    return src, http.get_json(_API), http.get_text(_HOURS)


def test_upice_monthly_observations_exclude_sundays_and_holiday(cfg, root, monkeypatch):
    src, posts, hours = upice_pages(cfg, root)
    events = src.parse(posts, hours)
    assert len(events) == 24
    assert all(e.start.year == 2026 and e.start.month == 11 for e in events)
    assert all(e.start.weekday() != 6 and e.start.day != 17 for e in events)
    assert all(e.start.strftime('%H:%M') == '18:00' and e.end.strftime('%H:%M') == '20:00' for e in events)
    assert all(e.venue == 'Hvězdárna v Úpici' and e.place_raw == 'Úpice' for e in events)
    assert all('jasného počasí' in e.description for e in events)
    assert len(flag_time(events, 60, ref=date(2026, 11, 3))) == 23
    before = [(e.source_id, e.start) for e in events]
    monkeypatch.setenv('MOSTEK_NOW', '2030-01-01')
    assert [(e.source_id, e.start) for e in src.parse(posts, hours)] == before


def test_upice_needs_authoritative_month_and_matching_table(cfg, root):
    from copy import deepcopy
    src, posts, hours = upice_pages(cfg, root)
    with pytest.raises(ValueError):
        src.parse([], hours)
    with pytest.raises(ValueError):
        src.parse(posts, '<table>Opening hours 10–20</table>')
    with pytest.raises(ValueError):
        src.parse(posts, hours.replace('18:00', '19:00'))
    broken = deepcopy(posts)
    for post in broken:
        if post['id'] == 6074:
            post['content']['rendered'] += '<p>Večerní pozorování se 10. listopadu nekoná.</p>'
    with pytest.raises(ValueError):
        src.parse(broken, hours)


def test_upice_easter_holidays_and_midnight_end(cfg, root):
    from mostek_kultura.sources.upice_observations import _czech_holidays
    src, _, hours = upice_pages(cfg, root)
    posts = [{
        'date': '2026-04-01T12:00:00', 'link': 'https://www.hvezdarnavupici.cz/?p=test',
        'title': {'rendered': 'Obloha a akce na úpické hvězdárně v dubnu 2026'},
        'content': {'rendered': '<p><strong>Začátky večerních pozorování:</strong></p><p>V dubnu začínají večerní pozorování noční oblohy z úpické hvězdárny pro veřejnost v 22 hodin a končí ve 24 hodin.</p>'},
    }]
    events = src.parse(posts, hours)
    assert {date(2026, 4, 3), date(2026, 4, 6)} <= _czech_holidays(2026)
    assert not any(e.start.date() in {date(2026, 4, 3), date(2026, 4, 6)} for e in events)
    assert all(e.end.day != e.start.day and e.end.hour == 0 for e in events)
    posts[0]['title']['rendered'] = 'Obloha a akce na úpické hvězdárně v srpnu 2026'
    with pytest.raises(ValueError):
        src.parse(posts, hours)


def test_upice_unparsed_table_exception_fails_closed(cfg, root):
    src, posts, hours = upice_pages(cfg, root)
    doc = BeautifulSoup(hours, 'html.parser')
    cell = doc.select('table.cla-text tr')[1].find_all('td', recursive=False)[2]
    cell.append(' (4. listopadu zavřeno)')
    with pytest.raises(ValueError):
        src.parse(posts, str(doc))


def test_jicin_active_public_recurrence_is_never_silently_lost(cfg, monkeypatch):
    monkeypatch.setenv('MOSTEK_NOW', '2026-11-03')
    src = source(cfg, 'hvezdarna-jicin')
    with pytest.raises(ValueError):
        src.parse_ics(calendar(ics_event('Veřejné pozorování', extra='RRULE:FREQ=WEEKLY;COUNT=5')))
    assert src.parse_ics(calendar(ics_event('Perseidy roj', extra='RRULE:FREQ=YEARLY'))) == []


def test_astrohk_direct_programme_wins_over_hkinfo(cfg):
    from copy import deepcopy
    from datetime import timedelta

    from mostek_kultura.normalize import dedupe

    html, issue = synthetic_hk(group='PŘEDNÁŠKY', item='29. 10. 18:00 | Vesmírné analogické mise')
    html = html.replace('Test description', 'Přímý popis').replace('<div class="odpoved">', '<div class="odpoved"><img src="/images/mission.jpg">')
    direct = source(cfg, 'astrohk').parse(html, issue)[0]
    direct.place = 'Hradec Králové'
    direct.end = direct.start + timedelta(minutes=90)
    aggregator = deepcopy(direct)
    aggregator.source = 'hradec-vyber'
    aggregator.title = 'Přednáška: Vesmírné analogické mise'
    aggregator.image = 'https://www.hkinfo.cz/old.jpg'
    aggregator.end = aggregator.start + timedelta(minutes=60)
    aggregator.description = 'Zkrácený popis agregátoru'
    merged = dedupe([aggregator, direct], {s.name: s.priority for s in cfg.sources})
    assert len(merged) == 1
    assert merged[0].source == 'astrohk'
    assert merged[0].title == 'Vesmírné analogické mise'
    assert merged[0].image == 'https://www.astrohk.cz/images/mission.jpg'
    assert merged[0].end == direct.start + timedelta(minutes=90)
    assert merged[0].description == 'Přímý popis'
    assert 'hradec-vyber' in merged[0].sources
