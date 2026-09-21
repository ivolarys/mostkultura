"""Render site/: index.html (data inlined), events.json, summary.json, status.json."""

from __future__ import annotations

import json
import shutil
import unicodedata
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import Config
from .dates import now, today
from .model import Event, SourceStatus

TEMPLATES = Path(__file__).parent / "templates"
STATIC = Path(__file__).parent / "static"


def _ev_public(e: Event, cfg: Config) -> dict:
    titles = {s.name: s.title for s in cfg.sources}
    sources = [e.source, *e.sources]
    return {
        "id": e.source_id,
        "title": e.title,
        "start": e.start.isoformat(),
        "end": e.end.isoformat() if e.end else None,
        "all_day": e.all_day,
        "ongoing": e.ongoing,
        "place": e.place,
        "venue": e.venue,
        "lat": e.lat,
        "lon": e.lon,
        "geo": e.geo,
        "category": e.category or "jine",
        "category_label": cfg.category_label(e.category),
        "url": e.url,
        "image": e.image,
        "description": (e.description or "")[:300],
        "sources": sources,
        "source_labels": [titles.get(s, s) for s in sources],
    }


def _bucket(events: list[Event], d_from: date, d_to: date) -> tuple[list[Event], list[Event]]:
    """Events starting in [d_from, d_to] and ongoing events overlapping it."""
    main, ongoing = [], []
    for e in events:
        sd = e.start.date()
        if e.ongoing and not (d_from <= sd <= d_to):
            ed = e.end.date() if e.end else sd
            if sd <= d_to and ed >= d_from:
                ongoing.append(e)
        elif d_from <= sd <= d_to:
            main.append(e)
    return main, ongoing


def build_summary(events: list[Event], cfg: Config, statuses: list[SourceStatus]) -> dict:
    t = today()
    weekend_start = t + timedelta(days=4 - t.weekday())
    ranges = {
        "today": (t, t),
        "tomorrow": (t + timedelta(days=1), t + timedelta(days=1)),
        "weekend": (weekend_start, weekend_start + timedelta(days=2)),
        "week": (t, t + timedelta(days=6)),
    }
    out = {"generated_at": now().isoformat(timespec="seconds"), "date": t.isoformat()}
    for key, (a, b) in ranges.items():
        main, ongoing = _bucket(events, a, b)
        out[key] = {
            "count": len(main),
            "ongoing_count": len(ongoing),
            "events": [{
                "title": e.title,
                "date": e.start.date().isoformat(),
                "time": None if e.all_day else e.start.strftime("%H:%M"),
                "place": e.place, "venue": e.venue,
                "category": cfg.category_label(e.category), "url": e.url,
            } for e in main[: cfg.summary_top_n]],
        }
    out["sources_ok"] = [s.name for s in statuses if s.status == "ok"]
    out["sources_failed"] = [s.name for s in statuses if s.status in ("fallback", "error")]
    return out


def plural_akce(n: int) -> str:
    return f"{n} akce" if n == 1 else f"{n} akce" if 2 <= n <= 4 else f"{n} akcí"


STATUS_LABEL = {"ok": "OK", "fallback": "záložní data", "error": "chyba", "disabled": "vypnuto"}


_CZECH_ORDER = {char: index for index, char in enumerate(
    "aáäbcčdďeéěfghijklmnňoópqrřsštťuúůvwxyzž"
)}
_CZECH_ORDER["ch"] = _CZECH_ORDER["h"] + 0.5


def _czech_sort_key(value: str) -> tuple:
    """Return a deterministic Czech collation key without locale state."""
    folded = unicodedata.normalize("NFC", value).casefold()
    primary = []
    index = 0
    while index < len(folded):
        pair = folded[index:index + 2]
        if pair == "ch":
            primary.append(_CZECH_ORDER["ch"])
            index += 2
            continue
        char = folded[index]
        decomposed = unicodedata.normalize("NFD", char)
        base = decomposed[0]
        # Vowel accents sort as their unaccented base; Czech consonant accents
        # retain their distinct alphabet positions.
        if base in "aeiouy" and all(unicodedata.combining(c) for c in decomposed[1:]):
            char = base
        primary.append(_CZECH_ORDER.get(char, len(_CZECH_ORDER) + ord(char)))
        index += 1
    return (tuple(primary), folded)


def build_sources_page(events: list[Event], cfg: Config, statuses: list[SourceStatus]) -> dict:
    """Sources grouped by municipality for zdroje.html."""
    st = {s.name: s for s in statuses}
    per_place: dict[str | None, int] = {}
    for e in events:
        per_place[e.place] = per_place.get(e.place, 0) + 1

    def info(s) -> dict:
        x = st.get(s.name)
        covers = []
        if s.type == "goout":
            covers = list(s.extra.get("venue_queries", []))
        return {
            "name": s.name, "title": s.title, "type": s.type, "page": s.page_url,
            "host": urlsplit(s.page_url).hostname or "",
            "status": x.status if x else "disabled",
            "status_label": STATUS_LABEL.get(x.status if x else "disabled", "?"),
            "count": x.count if x else 0,
            "fetched": (x.fetched_at or "")[:16].replace("T", " ") if x else "",
            "covers": covers,
        }

    groups = []
    for p in sorted(cfg.places, key=lambda place: _czech_sort_key(place.name)):
        srcs = [info(s) for s in cfg.sources if s.place == p.name]
        groups.append({"place": p.name, "aliases": p.aliases[:6], "sources": srcs,
                       "event_count": per_place.get(p.name, 0)})
    regional = [info(s) for s in cfg.sources if not s.place]
    return {"groups": groups, "regional": regional, "venues_allow": cfg.venues_allow}


def render_site(events: list[Event], cfg: Config, statuses: list[SourceStatus], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    events = sorted(events, key=lambda e: (e.start, e.title))
    payload = {
        "generated_at": now().isoformat(timespec="seconds"),
        "tz": cfg.timezone,
        "categories": [{"slug": c.slug, "label": c.label, "icon": c.icon} for c in cfg.categories],
        "places": [p.name for p in cfg.places],
        "events": [_ev_public(e, cfg) for e in events],
    }
    status = {"generated_at": payload["generated_at"], "sources": [asdict(s) for s in statuses]}
    summary = build_summary(events, cfg, statuses)

    (out_dir / "events.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")

    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    env.filters["akce"] = plural_akce
    tpl = env.get_template("index.html.j2")
    status_by_name = {source.name: source.status for source in statuses}
    # The homepage needs the complete configured catalog, rather than only
    # sources represented by currently visible events, to honor local prefs.
    html_payload = {**payload, "source_catalog": [{
        "name": source.name,
        "label": source.title,
        "place": source.place,
        "status": status_by_name.get(source.name, "error"),
    } for source in cfg.sources if source.enabled]}
    html = tpl.render(
        data_json=json.dumps(html_payload, ensure_ascii=False).replace("</", "<\\/"),
        status=status, generated_at=payload["generated_at"], count=len(events),
    )
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    zdroje = env.get_template("zdroje.html.j2").render(
        generated_at=payload["generated_at"], **build_sources_page(events, cfg, statuses))
    (out_dir / "zdroje.html").write_text(zdroje, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("")

    if STATIC.is_dir():
        for f in STATIC.iterdir():
            if f.is_file():
                shutil.copyfile(f, out_dir / f.name)
            elif f.is_dir():
                shutil.copytree(f, out_dir / f.name, dirs_exist_ok=True)
