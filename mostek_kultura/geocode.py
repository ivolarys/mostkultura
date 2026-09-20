"""Geocoding of event venues/places via a committed cache + throttled Nominatim lookups.

The cache (`cache/geocode.json`, committed like `cache/classifications.json`) maps
`normalize(venue) + "|" + normalize(place)` (or `"|" + normalize(place)` when there is no venue)
to a `{lat, lon, precision, q, ts}` entry. `precision` is "venue" (exact venue match), "place"
(municipality centroid, used as a fallback) or "none" (looked up, no usable result).
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from .config import Config
from .model import Event
from .normalize import norm

log = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "mostek-kultura/0.1 (+https://github.com/ivolarys/mostkultura)"
SLEEP_S = 1.1                       # Nominatim usage policy: max 1 request/second
STALE_DAYS = 30
BBOX = (50.15, 50.9, 15.1, 16.3)    # lat_min, lat_max, lon_min, lon_max (sanity check on results)

# Most whitelisted places are in okres Trutnov, so appending it disambiguates them from
# same-named settlements elsewhere in Czechia (e.g. there's an unrelated "Mostek" near Ústí nad
# Orlicí that a bare query resolves to instead). These aren't in okres Trutnov though, so a plain
# "<place>, Česko" is used instead, verified against the result's display_name (Jičín/Hořice/Nová
# Paka/Lázně Bělohrad/Pecka: okres Jičín; Jaroměř: okres Náchod).
_PLAIN_QUERY = {"Hradec Králové", "Jičín", "Jilemnice", "Hořice", "Nová Paka", "Lázně Bělohrad", "Pecka", "Jaroměř", "Turnov"}
# Josefov is a village within Jaroměř (okres Náchod); a bare "Josefov, Česko" resolves to an
# unrelated same-named village in okres Hodonín, so it needs its containing town spelled out.
_QUERY_OVERRIDE = {"Josefov": "Josefov, Jaroměř, Česko"}


def cache_key(venue: str | None, place: str | None) -> str:
    v, p = norm(venue), norm(place)
    return f"{v}|{p}" if v else f"|{p}"


def _place_query(place: str) -> str:
    if place in _QUERY_OVERRIDE:
        return _QUERY_OVERRIDE[place]
    if place in _PLAIN_QUERY:
        return f"{place}, Česko"
    return f"{place}, okres Trutnov, Česko"


MAX_VENUE_KM = 12.0  # a "venue" hit farther than this from its town is a mis-geocode


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km (haversine)."""
    from math import asin, cos, radians, sin, sqrt
    p1, p2 = radians(lat1), radians(lat2)
    a = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


def _in_bbox(lat: float, lon: float) -> bool:
    lat_min, lat_max, lon_min, lon_max = BBOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def _nominatim_get(q: str) -> list[dict]:
    """Raw Nominatim call. Separated out so tests can monkeypatch it without touching the network."""
    r = httpx.get(
        NOMINATIM_URL,
        params={"q": q, "format": "json", "limit": 1, "countrycodes": "cz"},
        headers={"User-Agent": USER_AGENT, "Accept-Language": "cs"},
        timeout=15.0,
    )
    r.raise_for_status()
    return r.json()


SETTLEMENT_TYPES = {"city", "town", "village", "municipality", "administrative", "hamlet",
                    "county", "state", "region", "district"}


def _lookup(q: str, place_check: str | None, venue: bool = False) -> tuple[float, float] | None:
    """Query Nominatim for `q`, return (lat, lon) or None on miss/error/sanity failure.

    With `venue=True` a result that is just a settlement (town/village…) counts as a miss, so an
    unknown venue name does not silently become a "venue"-precision town centroid.
    Never raises: network errors are logged and treated as a miss.
    """
    try:
        results = _nominatim_get(q)
    except Exception as e:  # noqa: BLE001
        log.warning("geocode: lookup failed for %r: %s", q, e)
        return None
    if not results:
        return None
    row = results[0]
    try:
        lat, lon = float(row["lat"]), float(row["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not _in_bbox(lat, lon):
        log.warning("geocode: %r -> (%s, %s) outside bbox, treating as miss", q, lat, lon)
        return None
    if venue and (row.get("addresstype") in SETTLEMENT_TYPES or row.get("type") in SETTLEMENT_TYPES):
        log.info("geocode: %r -> settlement %r, not venue-precise", q, row.get("display_name"))
        return None
    if place_check and norm(place_check) not in norm(row.get("display_name", "")):
        log.warning("geocode: %r -> display_name %r doesn't mention %r, treating as miss",
                    q, row.get("display_name"), place_check)
        return None
    return lat, lon


def _stale(entry: dict) -> bool:
    if entry.get("precision") != "none":
        return False
    ts = entry.get("ts")
    if not ts:
        return True
    try:
        age = datetime.now(UTC) - datetime.fromisoformat(ts)
    except ValueError:
        return True
    return age > timedelta(days=STALE_DAYS)


def load_cache(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                     encoding="utf-8")


_PREFIX = re.compile(r"^(ul\.|ulice|sál|sal|kde:?)\s+", re.IGNORECASE)
_VENUE_PART = re.compile(r"\s[–—]\s")


def venue_queries(venue: str, place: str) -> list[str]:
    """Candidate Nominatim queries for a venue string, most specific first.

    "Terapeutická zahrada, ul. Chelčického, Vrchlabí" -> the full string, then the part after the
    first comma (usually the street address), then the last address segment. Nominatim rarely knows
    business names but usually knows streets.
    """
    parts = [_PREFIX.sub("", p.strip()) for p in venue.split(",") if p.strip()]
    parts = [p for p in parts if p and norm(p) != norm(place)]
    cands: list[str] = []
    if parts:
        cands.append(", ".join(parts))
    if len(parts) > 1:
        cands.append(", ".join(parts[1:]))
        cands.append(parts[-1])
    if parts:
        # Nominatim commonly knows the institution but not an individual hall or foyer. An
        # explicit address is more precise, so keep existing address fallbacks ahead of it.
        institution = _VENUE_PART.split(parts[0], maxsplit=1)[0].strip()
        if institution and institution != parts[0]:
            cands.append(institution)
    out: list[str] = []
    for c in cands:
        q = f"{c}, {place}, Česko"
        if q not in out:
            out.append(q)
    return out[:3]


def _resolve(cache: dict, key: str, q: str | list[str], place_check: str, precision_on_hit: str,
             online: bool, budget: list[int], max_new: int, now_iso: str) -> dict | None:
    """Return the cache entry for `key`, doing live lookups (and caching) when eligible.

    `q` may be a list of candidate queries tried in order until one hits (each costs budget).
    """
    entry = cache.get(key)
    queries = [q] if isinstance(q, str) else list(q)
    if online and (entry is None or _stale(entry)) and budget[0] < max_new and queries:
        latlon = None
        used = queries[0]
        for used in queries:
            if budget[0] >= max_new:
                break
            time.sleep(SLEEP_S)
            latlon = _lookup(used, place_check, venue=precision_on_hit == "venue")
            budget[0] += 1
            if latlon:
                break
        if latlon:
            entry = {"lat": latlon[0], "lon": latlon[1], "precision": precision_on_hit,
                      "q": used, "ts": now_iso}
        else:
            entry = {"lat": None, "lon": None, "precision": "none", "q": queries[0], "ts": now_iso}
        cache[key] = entry
    return entry


def geocode_events(events: list[Event], cfg: Config, cache_path: Path, online: bool,
                    max_new: int = 40) -> dict:
    """Fill `lat`/`lon`/`geo` on each in-scope event and return the updated cache dict.

    Lookup order per event: venue+place key (used only when its precision is "venue") -> place
    key (used as a "place" precision centroid) -> nothing (`geo=None`). At most `max_new` new
    Nominatim lookups happen per call; anything past that budget falls back to whatever is already
    cached (typically the place centroid). `cache_path` is read at the start and the merged result
    is both returned and left for the caller to persist (mirrors `classify.load_cache`/`save_cache`).
    """
    cache = load_cache(cache_path)
    now_iso = datetime.now(UTC).isoformat(timespec="seconds")
    budget = [0]  # mutable int so _resolve can bump it across calls
    place_names = {p.name for p in cfg.places}

    if online:
        # Guarantee every whitelisted place has a centroid entry, independent of which events
        # happen to be in the current build (venue-less events always need somewhere to fall back to).
        for p in cfg.places:
            _resolve(cache, cache_key(None, p.name), _place_query(p.name), p.name, "place",
                     online, budget, max_new, now_iso)

    for e in events:
        if e.place not in place_names:
            e.lat = e.lon = e.geo = None
            continue

        entry = None
        if e.venue:
            vkey = cache_key(e.venue, e.place)
            entry = _resolve(cache, vkey, venue_queries(e.venue, e.place), e.place, "venue",
                             online, budget, max_new, now_iso)
            if entry and entry.get("precision") == "venue":
                centroid = cache.get(cache_key(None, e.place))
                if centroid and centroid.get("lat") is not None and _km(
                        entry["lat"], entry["lon"], centroid["lat"], centroid["lon"]) > MAX_VENUE_KM:
                    log.info("geocode: %r is %.0f km from %s, using the town centroid instead",
                             e.venue, _km(entry["lat"], entry["lon"], centroid["lat"], centroid["lon"]),
                             e.place)
                else:
                    e.lat, e.lon, e.geo = entry["lat"], entry["lon"], "venue"
                    continue

        pkey = cache_key(None, e.place)
        entry = _resolve(cache, pkey, _place_query(e.place), e.place, "place",
                         online, budget, max_new, now_iso)
        if entry and entry.get("precision") == "place":
            e.lat, e.lon, e.geo = entry["lat"], entry["lon"], "place"
        else:
            e.lat = e.lon = e.geo = None

    return cache
