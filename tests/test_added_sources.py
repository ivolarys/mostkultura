import json
import re
import shutil

from mostek_kultura.build import build
from mostek_kultura.config import load_config


NEW_SOURCES = {"biograf-jicin", "klub-kus"}


def test_new_sources_are_enabled_and_present_in_offline_build(root, tmp_path):
    staged_root = tmp_path / "project"
    staged_root.mkdir()
    shutil.copy2(root / "config.yaml", staged_root / "config.yaml")
    for source in NEW_SOURCES:
        shutil.copytree(root / "tests" / "fixtures" / source,
                        staged_root / "tests" / "fixtures" / source)

    cfg = load_config(staged_root / "config.yaml")
    configured = {source.name: source for source in cfg.sources if source.name in NEW_SOURCES}
    assert set(configured) == NEW_SOURCES
    assert all(source.enabled for source in configured.values())

    out_dir = tmp_path / "site"
    build(staged_root, out_dir, offline=True, use_llm=False, only=NEW_SOURCES, geocode=False)

    status = json.loads((out_dir / "status.json").read_text(encoding="utf-8"))
    by_name = {item["name"]: item for item in status["sources"]}
    assert set(by_name) == NEW_SOURCES
    assert all(by_name[name]["status"] == "ok" and by_name[name]["count"] > 0
               for name in NEW_SOURCES), by_name

    events = json.loads((out_dir / "events.json").read_text(encoding="utf-8"))["events"]
    expected_places = {"biograf-jicin": "Jičín", "klub-kus": "Turnov"}
    for source, place in expected_places.items():
        source_events = [event for event in events if source in event["sources"]]
        assert source_events
        assert all(event["place"] == place for event in source_events)

    html = (out_dir / "index.html").read_text(encoding="utf-8")
    homepage_data = json.loads(re.search(
        r'<script type="application/json" id="data">(.*?)</script>', html
    ).group(1))
    catalog = {source["name"]: source for source in homepage_data["source_catalog"]}
    assert NEW_SOURCES <= set(catalog)
    assert all(catalog[name]["status"] == "ok" for name in NEW_SOURCES)

    sources_page = (out_dir / "zdroje.html").read_text(encoding="utf-8")
    assert "Biograf Český ráj – Jičín" in sources_page
    assert "Klub Kus – Turnov" in sources_page
