"""Programme parser for Spolek Bezdružic in Pecka.

The home page deliberately separates the small current programme from a long
archive.  Its programme cards are image-only, so every current link is opened
and only details with explicit textual event metadata yield events.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

from ..dates import MONTHS, TZ
from ..model import Event
from .base import Source, clean, soup

_FESTIVAL_DATE = re.compile(
    r"\b(?P<day>\d{1,2})\.\s*(?P<month>[A-Za-zÁČĎÉĚÍŇÓŘŠŤÚŮÝŽáčďéěíňóřšťúůýž]+)\s+"
    r"(?P<year>\d{4})\s*-\s*od\s*(?P<hour>\d{1,2})[.:](?P<minute>\d{2})\s*hodin\b",
    re.IGNORECASE,
)
_BOOM_VISIBLE_TIMES = re.compile(
    r"\b(?P<day>\d{1,2})\.\s*(?P<month>led|úno|bře|dub|kvě|čvn|čvc|srp|zář|říj|lis|pro)\s+"
    r"(?P<year>\d{4})\s*\((?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})\)",
    re.IGNORECASE,
)
_BOOM_MONTHS = {"led": 1, "úno": 2, "bře": 3, "dub": 4, "kvě": 5, "čvn": 6,
                "čvc": 7, "srp": 8, "zář": 9, "říj": 10, "lis": 11, "pro": 12}


class BezdruzicSource(Source):
    """Read only the linked, current Bezdružic programme details."""

    def fetch(self, http) -> list[Event]:
        homepage = soup(http.get_text(self.cfg.url))
        links = self._upcoming_links(homepage)
        events: list[Event] = []
        for url in links:
            host = urlparse(url).hostname or ""
            path = urlparse(url).path.rstrip("/")
            if host == urlparse(self.cfg.url).hostname and path == "/pivo":
                # Kumraus is a product page. It has no textual event date and must not become a
                # made-up event merely because the current-programme section links to it.
                continue
            if host == urlparse(self.cfg.url).hostname and path == "/festival":
                url = f"{url.rstrip('/')}/"
                events.extend(self._parse_festival(http.get_text(url), url))
            elif host == "connect.boomevents.org":
                detail = http.get_text(url)
                events.extend(self._parse_boom(detail, url))
            else:
                raise ValueError(f"Bezdružic current programme has unsupported detail: {url}")
        return events

    def _upcoming_links(self, doc) -> list[str]:
        section = doc.select_one("#akce")
        if section is None:
            raise ValueError("Bezdružic programme section missing: #akce")
        heading = next((item for item in section.select("h3") if clean(item.get_text(" ")).lower().startswith("chystáme pro vás")), None)
        if heading is None:
            raise ValueError("Bezdružic current programme heading missing")

        links: list[str] = []
        for sibling in heading.next_siblings:
            if getattr(sibling, "name", None) == "h3":
                break
            for anchor in ([sibling] if getattr(sibling, "name", None) == "a" else sibling.select("a[href]") if getattr(sibling, "select", None) else []):
                href = clean(anchor.get("href"))
                if href:
                    url = urljoin(self.cfg.url, href)
                    parsed = urlparse(url)
                    home = urlparse(self.cfg.url)
                    if parsed.hostname == home.hostname and parsed.scheme != home.scheme:
                        url = parsed._replace(scheme=home.scheme).geturl()
                    if url not in links:
                        links.append(url)
        return links

    def _parse_festival(self, html: str, url: str) -> list[Event]:
        doc = soup(html)
        programme = doc.select_one("#program")
        title_el = programme.select_one("h1") if programme else None
        title = clean(title_el.get_text(" ")) if title_el else ""
        if not programme or not title:
            raise ValueError("Bezdružic festival detail lacks programme title")

        starts = [self._festival_start(clean(item.get_text(" "))) for item in programme.select("h3")]
        starts = [start for start in starts if start is not None]
        if not starts:
            raise ValueError("Bezdružic festival detail lacks explicit programme dates")

        intro = programme.select_one(".intro-text")
        image = doc.select_one("header.intro img[src]")
        return [self.event(
            title=title,
            start=start,
            url=url,
            place_raw=self.cfg.place,
            venue="Hrad Pecka",
            native_category="festival",
            description=clean(intro.get_text(" "))[:500] if intro else "",
            image=urljoin(url, image["src"]) if image else None,
            native_id=f"{url}|{start.isoformat()}",
        ) for start in starts]

    @staticmethod
    def _festival_start(text: str) -> datetime | None:
        match = _FESTIVAL_DATE.search(text)
        if match is None:
            return None
        month = MONTHS.get(match.group("month").lower())
        if month is None:
            raise ValueError(f"Bezdružic festival month unknown: {match.group('month')!r}")
        try:
            return datetime(
                int(match.group("year")), month, int(match.group("day")),
                int(match.group("hour")), int(match.group("minute")), tzinfo=TZ,
            )
        except ValueError as exc:
            raise ValueError(f"Bezdružic festival date invalid: {text!r}") from exc

    def _parse_boom(self, html: str, url: str) -> list[Event]:
        schema = self._boom_event_schema(html)
        title = clean(schema.get("name"))
        location = clean(schema.get("location"))
        if not title or not location:
            raise ValueError("Bezdružic BOOM event lacks title or location metadata")
        start = self._boom_date(schema.get("startDate"))
        end = self._boom_date(schema.get("endDate")) if schema.get("endDate") else None
        times = self._boom_visible_times(html, title, start.date())
        if times is not None:
            start, end = times
        elif end is not None:
            end = end.replace(hour=23, minute=59, second=59)
        return [self.event(
            title=title,
            start=start,
            end=end,
            all_day=times is None,
            url=clean(schema.get("url")) or url,
            place_raw=self.cfg.place,
            venue=location.split(",", 1)[0],
            description=clean(schema.get("description"))[:500],
            image=clean(schema.get("image")) or None,
            native_id=f"{url}|{start.isoformat()}",
        )]

    @staticmethod
    def _boom_event_schema(html: str) -> dict:
        for script in soup(html).select('script[type="application/ld+json"]'):
            try:
                payload = json.loads(script.string or script.get_text())
            except json.JSONDecodeError:
                continue
            items = payload if isinstance(payload, list) else [payload]
            for item in items:
                if isinstance(item, dict) and item.get("@type") == "Event":
                    return item
        raise ValueError("Bezdružic BOOM detail lacks Event JSON-LD")

    @staticmethod
    def _boom_date(value: object) -> datetime:
        if not isinstance(value, str):
            raise TypeError("Bezdružic BOOM event lacks date metadata")
        try:
            return datetime.strptime(value, "%d.%m.%Y").replace(tzinfo=TZ)
        except ValueError as exc:
            raise ValueError(f"Bezdružic BOOM date invalid: {value!r}") from exc

    @staticmethod
    def _boom_visible_times(html: str, title: str, expected_date: date) -> tuple[datetime, datetime] | None:
        doc = soup(html)
        heading = next((item for item in doc.select("h1") if clean(item.get_text(" ")) == title), None)
        header = heading.parent if heading is not None else None
        if header is None or "stackHeader" not in " ".join(header.get("class") or []):
            return None
        container = header.parent
        calendar = container.select_one("svg.bi-calendar4-week") if container is not None else None
        row = calendar.parent.parent if calendar is not None and calendar.parent is not None else None
        match = _BOOM_VISIBLE_TIMES.search(clean(row.get_text(" "))) if row is not None else None
        if match is None:
            return None
        month = _BOOM_MONTHS[match.group("month").lower()]
        year, day = int(match.group("year")), int(match.group("day"))
        start_hour, start_minute = (int(part) for part in match.group("start").split(":"))
        end_hour, end_minute = (int(part) for part in match.group("end").split(":"))
        try:
            start = datetime(year, month, day, start_hour, start_minute, tzinfo=TZ)
            end = datetime(year, month, day, end_hour, end_minute, tzinfo=TZ)
        except ValueError as exc:
            raise ValueError(f"Bezdružic BOOM visible time invalid: {match.group(0)!r}") from exc
        if start.date() != expected_date or end <= start:
            raise ValueError(f"Bezdružic BOOM visible time disagrees with Event metadata: {match.group(0)!r}")
        return start, end
