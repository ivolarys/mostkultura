"""Hrad Pecka uses Galileo's older event-list template."""

from mostek_kultura.config import SourceConfig
from mostek_kultura.http import FixtureHttp
from mostek_kultura.sources.galileo import GalileoSource

URL = "https://www.hradpecka.cz/cs/akce/"


def _source():
    return GalileoSource(SourceConfig(
        name="hrad-pecka", type="galileo", url=URL, place="Pecka",
    ))


def test_hrad_pecka_current_empty_program_is_valid(root):
    """The sidebar calendar has past links, but the actual current list is empty."""
    events = _source().fetch(FixtureHttp(root / "tests" / "fixtures" / "hrad-pecka"))
    assert events == []


def test_hrad_pecka_filtered_archive_uses_galileo_old_template(root):
    html = (root / "tests" / "fixtures" / "hrad-pecka" / "d454811e6e0f.html").read_text(encoding="utf-8")
    events = _source().parse(html)

    assert len(events) == 3
    potlach = next(event for event in events if event.title == "Trampský potlach")
    assert potlach.start.strftime("%Y-%m-%d %H:%M") == "2026-09-19 16:00"
    assert not potlach.all_day
    assert potlach.venue == "Hrad Pecka, Pecka"
    assert potlach.description == "tradiční setkání trampů na hradě Pecka"
    assert potlach.url == "https://www.hradpecka.cz/cs/akce/trampsky-potlach-207_155cs.html"
    assert potlach.native_id == "event-207"
