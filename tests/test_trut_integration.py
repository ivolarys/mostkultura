from datetime import date

from mostek_kultura.build import fetch_all
from mostek_kultura.classify import classify
from mostek_kultura.normalize import PlaceResolver, flag_time, in_scope, resolve_places
from mostek_kultura.render import build_sources_page


def test_trut_recording_survives_pipeline_and_expires(root, cfg):
    events, statuses = fetch_all(cfg, root, offline=True, only={"trut"}, persist=False)
    assert len(statuses) == 1 and statuses[0].status == "ok"
    assert statuses[0].count == 1
    events = flag_time(events, cfg.horizon_days, ref=date(2026, 9, 16))
    resolver = PlaceResolver(cfg)
    resolve_places(events, resolver, {s.name: s.place for s in cfg.sources})
    classify(events, cfg, {}, use_llm=False)
    assert len(events) == 1
    event = events[0]
    assert event.place == "Trutnov" and in_scope(event, resolver)
    assert event.category in cfg.category_slugs
    assert not event.all_day and not event.ongoing
    assert event.venue is None
    assert flag_time(events, cfg.horizon_days, ref=date(2026, 9, 17)) == []

    groups = build_sources_page([], cfg, statuses)["groups"]
    trutnov = next(group for group in groups if group["place"] == "Trutnov")
    assert "trut" in {source["name"] for source in trutnov["sources"]}
