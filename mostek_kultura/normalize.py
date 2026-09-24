"""Place resolution, scope filtering, time flags and cross-source deduplication."""

from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from datetime import date, timedelta

from .config import Config, SourceConfig
from .dates import today
from .model import Event

log = logging.getLogger(__name__)

_TITLE_PREFIX = re.compile(r"^(koncert|divadlo|vystava|prednaska|beseda|film|kino)\s*[:\-–]\s*")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", strip_accents(s or "").lower()).strip()


def norm_title(s: str) -> str:
    t = norm(s)
    t = _TITLE_PREFIX.sub("", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:40]


def _full_exhibition_title(s: str) -> str:
    """Normalize a whole title, ignoring only an exhibition label at either edge."""
    words = re.sub(r"[^a-z0-9 ]+", " ", norm(s)).split()
    if words and words[0] == "vystava":
        words.pop(0)
    if words and words[-1] == "vystava":
        words.pop()
    return " ".join(words)


class PlaceResolver:
    def __init__(self, cfg: Config):
        pairs: list[tuple[str, str]] = []
        for p in cfg.places:
            for alias in [p.name, *p.aliases]:
                pairs.append((norm(alias), p.name))
        pairs.sort(key=lambda x: -len(x[0]))
        self.patterns = [(re.compile(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])"), name)
                         for a, name in pairs if a]
        self.names = {p.name for p in cfg.places}
        self.venues_allow = [norm(v) for v in cfg.venues_allow]

    def resolve(self, *texts: str | None) -> str | None:
        for text in texts:
            t = norm(text)
            if not t:
                continue
            for pat, name in self.patterns:
                if pat.search(t):
                    return name
        return None

    def venue_allowed(self, *texts: str | None) -> bool:
        blob = " | ".join(norm(t) for t in texts if t)
        return any(v and v in blob for v in self.venues_allow)


def apply_source_filters(events: list[Event], scfg: SourceConfig) -> list[Event]:
    out = events
    if scfg.exclude_title:
        rx = re.compile(scfg.exclude_title)
        out = [e for e in out if not rx.search(e.title)]
    if scfg.max_events:
        out = sorted(out, key=lambda e: e.start)[: scfg.max_events]
    return out


def flag_time(events: list[Event], horizon_days: int, ref: date | None = None) -> list[Event]:
    """Drop past events, drop events beyond horizon, mark long multi-day events as ongoing."""
    ref = ref or today()
    horizon = ref + timedelta(days=horizon_days)
    out = []
    for e in events:
        sd = e.start.date()
        ed = e.end.date() if e.end else sd
        e.ongoing = bool(e.end) and (ed - sd) >= timedelta(days=2) and sd <= ref <= ed
        if ed < ref:
            continue
        if sd > horizon and not e.ongoing:
            continue
        out.append(e)
    return out


def resolve_places(events: list[Event], resolver: PlaceResolver,
                   defaults: dict[str, str | None] | None = None) -> None:
    """Order: explicit place from source, venue, then title/description, then the source default."""
    defaults = defaults or {}
    for e in events:
        if e.place in resolver.names:
            continue
        # A resolvable venue is more specific than a resolvable place_raw for its containing town,
        # so it wins; place_raw is still the fallback when the venue doesn't resolve to anything.
        e.place = resolver.resolve(e.venue) or resolver.resolve(e.place_raw)
        if e.place is None and not e.place_raw:
            e.place = resolver.resolve(e.title, e.description)
        if e.place is None:
            d = defaults.get(e.source)
            if d in resolver.names and not e.place_raw:
                e.place = d


def in_scope(e: Event, resolver: PlaceResolver) -> bool:
    return e.place in resolver.names or resolver.venue_allowed(e.venue, e.title)


def _similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    if len(shorter) >= 12 and shorter in longer:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def _merge(winner: Event, loser: Event, *, preserve_start: bool = False) -> Event:
    for f in ("end", "venue", "description", "image", "native_category", "place"):
        if not getattr(winner, f) and getattr(loser, f):
            setattr(winner, f, getattr(loser, f))
    if winner.all_day and not loser.all_day and not preserve_start:
        winner.start, winner.all_day = loser.start, False
    for s in [loser.source, *loser.sources]:
        if s not in winner.sources and s != winner.source:
            winner.sources.append(s)
    for u in [loser.url, *loser.urls]:
        if u and u != winner.url and u not in winner.urls:
            winner.urls.append(u)
    return winner


def _same_ongoing_exhibition(a: Event, b: Event) -> bool:
    """Match source date discrepancies only for the same exhibition running now."""
    if (a.source == b.source or not a.ongoing or not b.ongoing
            or a.category != "vystava" or b.category != "vystava"
            or not a.place or a.place != b.place
            or a.start.date() == b.start.date()
            or not a.end or not b.end
            or max(a.start.date(), b.start.date()) > min(a.end.date(), b.end.date())):
        return False
    title = _full_exhibition_title(a.title)
    if not title or title != _full_exhibition_title(b.title):
        return False
    va, vb, place = norm(a.venue), norm(b.venue), norm(a.place)
    return bool(va and vb and va != place and vb != place
                and (va in vb or vb in va))


def dedupe(events: list[Event], priorities: dict[str, int]) -> list[Event]:
    """Merge the same event reported by several sources. Higher priority source wins."""
    events = sorted(events, key=lambda e: (-priorities.get(e.source, 0), e.start))
    buckets: dict[tuple[date, str | None], list[Event]] = {}
    ongoing_exhibitions: dict[str, list[Event]] = {}
    out: list[Event] = []
    for e in events:
        key = (e.start.date(), e.place)
        nt = norm_title(e.title)
        found = None
        for cand in buckets.get(key, []):
            timed_different = not e.all_day and not cand.all_day and e.start != cand.start
            actual_venues = (
                e.venue and cand.venue and norm(e.venue) != norm(e.place)
                and norm(cand.venue) != norm(cand.place)
            )
            venue_incompatible = (
                actual_venues and norm(e.venue) not in norm(cand.venue)
                and norm(cand.venue) not in norm(e.venue)
            )
            if not timed_different and not venue_incompatible and _similar(nt, norm_title(cand.title)):
                found = cand
                break
        cross_date = False
        if not found and e.ongoing and e.category == "vystava" and e.place:
            for cand in ongoing_exhibitions.get(e.place, []):
                if _same_ongoing_exhibition(e, cand):
                    found = cand
                    cross_date = True
                    break
        if found:
            _merge(found, e, preserve_start=cross_date)
        else:
            buckets.setdefault(key, []).append(e)
            out.append(e)
            if e.ongoing and e.category == "vystava" and e.place:
                ongoing_exhibitions.setdefault(e.place, []).append(e)
    return out
