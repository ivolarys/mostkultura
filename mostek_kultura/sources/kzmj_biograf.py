"""Biograf Český ráj (KZMJ) programme at kzmj.cz/biograf/.

The server renders every programme item three times for small, medium and large
viewports.  The page has no pagination: the complete programme is in the one
response.  Parsing only ``.for-small`` prevents the responsive copies from
turning into duplicate events.  Its date is explicit including year and local
time; the colour-palette metadata is the published type of a non-film event.
Film-section entries include Royal Opera and ballet broadcasts, which are
programmed as cinema screenings and therefore remain ``Film``.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from ..dates import TZ
from ..model import Event
from .base import Source, clean, soup

_DATE = re.compile(
    r"^\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\s+\S+\s+(\d{1,2}):(\d{2})\s*$"
)
_VENUE = "Biograf Český ráj"


class KzmjBiografSource(Source):
    """Read KZMJ's complete server-rendered cinema and live-event listing."""

    def fetch(self, http) -> list[Event]:
        return self.parse(http.get_text(self.cfg.url))

    def parse(self, html: str) -> list[Event]:
        doc = soup(html)
        heading = doc.select_one("h1")
        if not heading or "biograf český ráj" not in clean(heading.get_text()).casefold():
            raise ValueError("KZMJ Biograf listing markup missing its programme heading")

        cards = doc.select(".for-small")
        # A real empty programme retains its heading but contains no responsive item cards.
        if not cards:
            if doc.select(".for-medium, .for-large, .list-col-nazev"):
                raise ValueError("KZMJ Biograf listing changed responsive event markup")
            return []

        events: list[Event] = []
        seen: set[str] = set()
        for card in cards:
            event = self._parse_card(card)
            if event.native_id not in seen:
                seen.add(event.native_id)
                events.append(event)
        return events

    def _parse_card(self, card) -> Event:
        date_el = card.select_one(".list-col-datum")
        link = card.select_one("a.list-col-nazev[href]")
        category_icon = card.select_one("ion-icon[name='color-palette-outline']")
        if not date_el or not link or not category_icon:
            raise ValueError("KZMJ Biograf listing contains a malformed event card")

        title = clean(link.get_text())
        if not title:
            raise ValueError("KZMJ Biograf listing contains an event card without a title")
        start = self._parse_start(clean(date_el.get_text(" ")))
        href = clean(link.get("href"))
        if not href:
            raise ValueError("KZMJ Biograf listing contains an event card without a detail URL")
        url = urljoin(self.cfg.url, href)

        category_box = category_icon.find_parent("div", class_="col-12")
        published_type = clean(category_box.get_text(" ")) if category_box else ""
        if not published_type:
            raise ValueError("KZMJ Biograf listing contains an event card without a published type")
        is_film = "/sekce-biograf/" in url
        image = card.select_one("img[src]")

        # Detail URLs recur for each projection, so the local start makes the ID stable and
        # distinct for repeats of the same title.
        return self.event(
            title=title,
            start=start,
            all_day=False,
            url=url,
            venue=_VENUE,
            place_raw=self.cfg.place,
            category=self._category(published_type, is_film),
            native_category="Film" if is_film else published_type,
            image=urljoin(self.cfg.url, image["src"]) if image else None,
            native_id=f"{url}|{start.isoformat()}",
        )

    @staticmethod
    def _category(published_type: str, is_film: bool) -> str | None:
        """Map KZMJ's programme type where the global category map has no equivalent."""
        if is_film:
            return "film"
        kind = published_type.casefold()
        if "koncert" in kind:
            return "koncert"
        if any(word in kind for word in ("stand-up", "comedy club", "divadlo")):
            return "divadlo"
        if any(word in kind for word in ("diashow", "talkshow", "přednáška", "prednaska", "beseda")):
            return "prednaska"
        return None

    @staticmethod
    def _parse_start(text: str) -> datetime:
        match = _DATE.fullmatch(text)
        if not match:
            raise ValueError(f"KZMJ Biograf event has invalid explicit date: {text!r}")
        day, month, year, hour, minute = (int(part) for part in match.groups())
        try:
            return datetime(year, month, day, hour, minute, tzinfo=TZ)
        except ValueError as exc:
            raise ValueError(f"KZMJ Biograf event has invalid explicit date: {text!r}") from exc
