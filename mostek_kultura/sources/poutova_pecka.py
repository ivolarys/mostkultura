"""Programme parser for the annual Pouťová Pecka festival.

The home page exposes an explicitly dated programme under ``#program``.  It
also confirms that the fair occupies Pecka's square, so entries without their
own location use ``Náměstí Pecka``.  The parser intentionally does not create
one duplicate all-day festival event: each timed programme item is an event.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from ..dates import TZ
from ..model import Event
from .base import Source, clean, soup

_DAY = re.compile(
    r"(?:pondělí|úterý|středa|čtvrtek|pátek|sobota|neděle)\s+"
    r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{4})",
    re.IGNORECASE,
)
_WEEKDAY = re.compile(r"^(?:pondělí|úterý|středa|čtvrtek|pátek|sobota|neděle)\b", re.IGNORECASE)
_TIME = re.compile(r"^\s*(?P<hour>\d{1,2})[.:](?P<minute>\d{2})\s*hodin\b", re.IGNORECASE)
_PARENTHESIS = re.compile(r"\((?P<text>[^()]*)\)")
_LOCATION = re.compile(r"\b(?:na|v|ve|před)\s+(?P<venue>[^,()]+)", re.IGNORECASE)

_DEFAULT_VENUE = "Náměstí Pecka"
_GENRE_PATTERNS = (
    re.compile(r"\bloutková\s+pohádka\b", re.IGNORECASE),
    re.compile(r"\bdivadelní\s+pohádka\b", re.IGNORECASE),
    re.compile(r"\bdivadlení\s+pohádka\b", re.IGNORECASE),  # typo on the page
    re.compile(r"\bkoncert\b", re.IGNORECASE),
    re.compile(r"\b(?:ohňová\s+show|hasičská\s+pouťová\s+zábava)\b", re.IGNORECASE),
    re.compile(r"\bzávod\s+na\s+běžkách\b", re.IGNORECASE),
    re.compile(r"\bmše\s+svatá\b", re.IGNORECASE),
)


class PoutovaPeckaSource(Source):
    def fetch(self, http) -> list[Event]:
        return self.parse(http.get_text(self.cfg.url))

    def parse(self, html: str) -> list[Event]:
        doc = soup(html)
        programme = doc.select_one("#program")
        if programme is None:
            raise ValueError("Pouťová Pecka programme missing: #program")

        days = []
        for heading in programme.select("h3"):
            heading_text = clean(heading.get_text(" "))
            if not _WEEKDAY.match(heading_text):
                continue
            match = _DAY.fullmatch(heading_text)
            if match is None:
                raise ValueError(f"Pouťová Pecka day lacks explicit numeric year: {heading_text!r}")
            days.append((heading, match))
        if not days:
            raise ValueError("Pouťová Pecka programme lacks dated days")

        image = doc.select_one("header.intro img[src]")
        banner = urljoin(self.cfg.url, image["src"]) if image else None
        url = urljoin(self.cfg.page_url, "#program")
        events: list[Event] = []
        for heading, match in days:
            year, month, day = (int(match.group(key)) for key in ("year", "month", "day"))
            try:
                date = datetime(year, month, day, tzinfo=TZ)
            except ValueError as exc:
                raise ValueError(f"Pouťová Pecka day invalid: {heading.get_text(' ', strip=True)!r}") from exc
            for item in self._day_items(heading):
                event = self._parse_item(item, date, url, banner)
                if event is not None:
                    events.append(event)
        if not events:
            raise ValueError("Pouťová Pecka programme lacks timed items")
        return events

    @staticmethod
    def _day_items(heading):
        for sibling in heading.next_siblings:
            if getattr(sibling, "name", None) == "h3":
                return
            if getattr(sibling, "name", None) == "p":
                yield sibling

    def _parse_item(self, item, date: datetime, url: str, image: str | None) -> Event | None:
        text = clean(item.get_text(" "))
        time = _TIME.match(text)
        title_tag = item.find("b")
        title = clean(title_tag.get_text(" ")) if title_tag else ""
        if not title and time is not None:
            # One real entry has an empty <b></b>; its following text is the
            # performer name, not a reason to discard a timed programme item.
            title = next((clean(part) for part in item.stripped_strings
                          if not _TIME.match(clean(part)) and not clean(part).startswith("(")), "")
        if time is None or not title:
            return None
        try:
            start = date.replace(hour=int(time.group("hour")), minute=int(time.group("minute")))
        except ValueError as exc:
            raise ValueError(f"Pouťová Pecka time invalid: {text!r}") from exc

        detail = clean(text[time.end():])
        detail = clean(detail.removeprefix(title))
        note = next((clean(match.group("text")) for match in _PARENTHESIS.finditer(detail)), "")
        venue = self._venue(note) or _DEFAULT_VENUE
        native_category = self._native_category(note, title)
        description = clean(detail)[:500]
        return self.event(
            title=title,
            start=start,
            url=url,
            place_raw=self.cfg.place,
            venue=venue,
            native_category=native_category,
            description=description,
            image=image,
            native_id=f"{start.isoformat()}|{title}",
        )

    @staticmethod
    def _venue(note: str) -> str | None:
        match = _LOCATION.search(note)
        if match is None:
            return None
        venue = clean(match.group("venue"))
        if not venue:
            return None
        normalized = venue.lower()
        if normalized in {"náměstí", "podiu", "pódiu", "stanu"}:
            return _DEFAULT_VENUE
        if normalized == "hasičárnou":
            return "Před hasičárnou, Pecka"
        if normalized.startswith("kostele "):
            church = re.sub(r"\s+v\s+pecce$", "", venue[len("kostele "):], flags=re.IGNORECASE)
            return "Kostel " + church + ", Pecka"
        return venue[:1].upper() + venue[1:]

    @staticmethod
    def _native_category(note: str, title: str) -> str | None:
        for pattern in _GENRE_PATTERNS:
            match = pattern.search(note) or pattern.search(title)
            if match:
                return clean(match.group(0)).lower()
        return None
