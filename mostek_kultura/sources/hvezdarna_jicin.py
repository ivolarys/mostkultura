"""Public observatory events from the first Hvězdárna Jičín calendar."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, time, timedelta
from html import unescape
from urllib.parse import urlsplit

from ..dates import TZ, today
from ..model import Event
from ..normalize import norm
from .base import Source, clean, soup

_EVENT = re.compile(r"BEGIN:VEVENT\r?\n(.*?)END:VEVENT", re.DOTALL)
_STAMP = re.compile(r"\d{8}T\d{6}Z?")
_DAY = re.compile(r"\d{8}")
_LINK = re.compile(r"https?://(?:www\.)?hvezdarnajicin\.cz/[^\s<>\"']+", re.IGNORECASE)
_PUBLIC = re.compile(
    r"\b(?:prednask|pozorovan|pozorvan|besed|noc ved|den (?:a noc na )?hvezdaren|"
    r"den a noc na hvezdarne|verejn.*(?:hra|pozorovan)|venkovni hra|"
    r"zatmeni|perseidy|jupiterova zkouska|hodina zeme|otevreni hvezdarny)"
)
_EXCLUDED = re.compile(r"\b(?:zrusen|skol|uklid|krouzk|obsazen|tabor|soukrom|pronajem|porad)")
_EPHEMERIS = re.compile(r"\bperseidy roj\b")
log = logging.getLogger(__name__)


def _fields(block: str) -> dict[str, tuple[str, str]]:
    fields = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        name = key.split(";", 1)[0].upper()
        fields[name] = (key, value)
    return fields


def _value(fields: dict[str, tuple[str, str]], key: str) -> str:
    return fields.get(key, ("", ""))[1]


def _date(fields: dict[str, tuple[str, str]], key: str) -> tuple[datetime | None, bool]:
    param, value = fields.get(key, ("", ""))
    if not value:
        return None, False
    if "VALUE=DATE" in param.upper() or _DAY.fullmatch(value):
        if not _DAY.fullmatch(value):
            raise ValueError(f"Hvězdárna Jičín invalid {key}: {value!r}")
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=TZ), True
    if not _STAMP.fullmatch(value):
        raise ValueError(f"Hvězdárna Jičín invalid {key}: {value!r}")
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).astimezone(TZ), False
    if "TZID=Europe/Prague" not in param:
        raise ValueError(f"Hvězdárna Jičín unsupported {key} timezone: {param!r}")
    return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=TZ), False


def _public_title(title: str) -> bool:
    normalized = norm(title)
    return bool(_PUBLIC.search(normalized)) and not _EXCLUDED.search(normalized)


class HvezdarnaJicinSource(Source):
    def fetch(self, http) -> list[Event]:
        events = self.parse_ics(http.get_text(self.cfg.url))
        first = today()
        last = first + timedelta(days=60)
        for event in events:
            if not (first <= event.start.date() <= last) or event.url == self.cfg.page_url:
                continue
            try:
                page = soup(http.get_text(event.url))
                image = page.select_one("main figure.wp-block-post-featured-image img[src]")
                excerpt = page.select_one("main .wp-block-post-excerpt")
                heading = page.select_one("main .wp-block-post-title")
                if heading and clean(heading.get_text(" ")):
                    event.title = clean(heading.get_text(" "))
                if image:
                    event.image = image["src"]
                if excerpt:
                    event.description = clean(excerpt.get_text(" "))[:500]
            except Exception as exc:  # noqa: BLE001
                # The calendar itself is authoritative; detail enrichment is optional.
                log.warning("%s: detail %s unavailable: %s", self.name, event.url, exc)
        return events

    def parse_ics(self, text: str) -> list[Event]:
        unfolded = re.sub(r"\r?\n[ \t]", "", text)
        if "BEGIN:VCALENDAR" not in unfolded or "END:VCALENDAR" not in unfolded:
            raise ValueError("Hvězdárna Jičín calendar markup missing")
        if unfolded.count("BEGIN:VEVENT") != unfolded.count("END:VEVENT"):
            raise ValueError("Hvězdárna Jičín calendar has an incomplete event")
        events = []
        for block in _EVENT.findall(unfolded):
            fields = _fields(block)
            title = clean(unescape(_value(fields, "SUMMARY")).replace(r"\,", ","))
            if not _public_title(title) or _EPHEMERIS.search(norm(title)):
                continue
            if _value(fields, "STATUS").upper() == "CANCELLED":
                continue
            if "RRULE" in fields:
                rule = _value(fields, "RRULE")
                until_match = re.search(r"(?:^|;)UNTIL=(\d{8})(?:T\d{6}Z?)?(?:;|$)", rule)
                if until_match and datetime.strptime(until_match.group(1), "%Y%m%d").replace(tzinfo=TZ).date() < today():
                    continue
                raise ValueError(f"Hvězdárna Jičín active public recurrence unsupported: {title!r}")
            start, all_day = _date(fields, "DTSTART")
            if start is None:
                raise ValueError(f"Hvězdárna Jičín public event lacks DTSTART: {title!r}")
            end, end_all_day = _date(fields, "DTEND")
            if all_day and end is not None:
                if not end_all_day:
                    raise ValueError(f"Hvězdárna Jičín all-day event has timed DTEND: {title!r}")
                end = datetime.combine(end.date() - timedelta(days=1), time.max, tzinfo=TZ)
            if end is not None and end <= start:
                raise ValueError(f"Hvězdárna Jičín event has invalid end: {title!r}")
            uid = _value(fields, "UID")
            if not uid:
                raise ValueError(f"Hvězdárna Jičín public event lacks UID: {title!r}")
            description = clean(unescape(_value(fields, "DESCRIPTION")).replace(r"\n", " "))
            match = re.search(r'href="(https?://[^\"]+)"', description)
            href = unescape(match.group(1)) if match else ""
            if not href:
                plain = _LINK.search(description)
                href = plain.group() if plain and "google.com/url?q=" not in description else ""
            url = href.rstrip(".,);/") + "/" if urlsplit(href).hostname in {
                "hvezdarnajicin.cz", "www.hvezdarnajicin.cz"
            } else self.cfg.page_url
            venue = clean(unescape(_value(fields, "LOCATION")).replace(r"\,", ",")) or "Hvězdárna Jičín"
            if not _value(fields, "LOCATION") and ("venkovni hra" in norm(title) or "venkovni hra" in norm(description)):
                venue = None
            events.append(self.event(
                title=title,
                start=start,
                end=end,
                all_day=all_day,
                url=url,
                place_raw=self.cfg.place,
                venue=venue,
                native_category="Přednáška" if "prednask" in norm(title) or "besed" in norm(title) else None,
                description=re.sub(r"<[^>]+>", " ", description)[:500],
                native_id=f"{uid}|{start.isoformat()}",
            ))
        return events
