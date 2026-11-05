"""Jazz Goes To Town festival programme from its server-rendered listing."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from ..dates import TZ
from ..model import Event
from .base import Source, clean, soup

_MONTHS = {
    "leden": 1, "únor": 2, "březen": 3, "duben": 4, "květen": 5, "červen": 6,
    "červenec": 7, "srpen": 8, "září": 9, "říjen": 10, "listopad": 11, "prosinec": 12,
}
_FESTIVAL_DATE = re.compile(
    r"\b\d{1,2}\.\s*[–-]\s*\d{1,2}\.\s*"
    r"(?P<month>leden|únor|březen|duben|květen|červen|červenec|srpen|září|říjen|listopad|prosinec)"
    r"\s+(?P<year>\d{4})\b",
    re.IGNORECASE,
)
_SECTION_DATE = re.compile(r"\S+\s+(?P<day>\d{1,2})/(?P<month>\d{1,2})")
_TIME = re.compile(r"(?P<hour>\d{1,2})[.:](?P<minute>\d{2})")
_VENUES = {"Muzeum východních Čech": "Muzeum východních Čech v Hradci Králové"}


class JgttSource(Source):
    """Read one event per programme card, including combined concert bills."""

    def fetch(self, http) -> list[Event]:
        return self.parse(http.get_text(self.cfg.url))

    def parse(self, html: str) -> list[Event]:
        doc = soup(html)
        wrapper = doc.select_one(".event-list-wrapper")
        if wrapper is None:
            raise ValueError("Jazz Goes To Town programme wrapper missing")
        listing = wrapper.select_one(".event-list")
        if listing is None:
            if not clean(wrapper.get_text(" ")) and not wrapper.find(True):
                return []
            raise ValueError("Jazz Goes To Town programme list missing")

        sections = listing.select(".event-list-section")
        if not sections:
            if listing.select("article.event") or clean(listing.get_text(" ")):
                raise ValueError("Jazz Goes To Town programme sections missing")
            return []

        festival_dates = {
            (int(match.group("year")), _MONTHS[match.group("month").lower()])
            for tag in doc.select(".marquee__text")
            if (match := _FESTIVAL_DATE.search(clean(tag.get_text(" "))))
        }
        if len(festival_dates) != 1:
            raise ValueError("Jazz Goes To Town festival year missing or ambiguous")
        year, festival_month = festival_dates.pop()

        events: list[Event] = []
        for section in sections:
            heading = section.select_one("h2.event-list-section__title")
            day_match = _SECTION_DATE.fullmatch(clean(heading.get_text(" "))) if heading else None
            if day_match is None:
                raise ValueError("Jazz Goes To Town programme day malformed")
            day, month = int(day_match.group("day")), int(day_match.group("month"))
            if month != festival_month:
                raise ValueError("Jazz Goes To Town programme month differs from festival date")
            cards = section.select("article.event")
            if not cards:
                raise ValueError("Jazz Goes To Town programme day has no event cards")
            for card in cards:
                events.append(self._parse_card(card, year, month, day))
        return events

    def _parse_card(self, card, year: int, month: int, day: int) -> Event:
        link = card.select_one(".event__title a[href]")
        time_tag = card.select_one(".event__meta-item--time")
        venue_tag = card.select_one(".event__meta-item--venue")
        if link is None or time_tag is None or venue_tag is None:
            raise ValueError("Jazz Goes To Town event card missing title, time, or venue")
        title = clean(link.get_text(" "))
        href = clean(link.get("href"))
        venue = clean(venue_tag.get_text(" "))
        time_match = _TIME.fullmatch(clean(time_tag.get_text(" ")))
        if not title or not href or not venue or time_match is None:
            raise ValueError("Jazz Goes To Town event card malformed")
        try:
            start = datetime(
                year, month, day, int(time_match.group("hour")),
                int(time_match.group("minute")), tzinfo=TZ,
            )
        except ValueError as exc:
            raise ValueError("Jazz Goes To Town event card has invalid date or time") from exc
        url = urljoin(self.cfg.url, href)
        image = card.select_one(".event__artists img[src]")
        return self.event(
            title=title,
            start=start,
            url=url,
            place_raw=self.cfg.place,
            venue=_VENUES.get(venue, venue),
            native_category="Koncert",
            image=urljoin(self.cfg.url, image["src"]) if image else None,
            native_id=f"{url}|{start.isoformat()}",
        )
