"""Klub Kus programme at kulturaturnov.cz/klub-kus.

The venue publishes its future programme server-side in ``#programList``.  Each
card has a complete local ISO datetime, a detail link, poster and short
description.  Detail pages do not expose a usable event category, so the
parser deliberately leaves ``native_category`` empty instead of inferring one
from a performer, prose, or the recurring "Básníci ticha" series label.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from ..dates import TZ
from ..model import Event
from .base import Source, clean, soup


class KlubKusSource(Source):
    """Read the venue-only programme embedded on the Klub Kus landing page."""

    def fetch(self, http) -> list[Event]:
        return self.parse(http.get_text(self.cfg.url))

    def parse(self, html: str) -> list[Event]:
        listing = soup(html).select_one("#programList .program-list")
        if listing is None:
            raise ValueError("Klub Kus programme markup missing #programList .program-list")

        cards = listing.select("article")
        # A present, empty programme list is the site's valid no-events state.  By contrast, a
        # card with missing required fields signals changed markup and must preserve last_good.
        if not cards:
            return []
        return [self._parse_card(card) for card in cards]

    def _parse_card(self, card) -> Event:
        time_el = card.select_one("time[datetime]")
        title_el = card.select_one("h2")
        link = card.select_one("a[href]")
        if not time_el or not title_el or not link:
            raise ValueError("Klub Kus programme contains a malformed event card")

        start = self._parse_start(time_el.get("datetime"))
        title = clean(title_el.get_text(" "))
        href = clean(link.get("href"))
        if not title or not href:
            raise ValueError("Klub Kus programme contains an event card without title or link")

        image = card.select_one("img[src]")
        description = " ".join(
            clean(p.get_text(" ")) for p in card.select("h2 ~ p:not(.event_note)")
            if clean(p.get_text(" "))
        )
        url = urljoin(self.cfg.url, href)
        # The portal reuses individual detail URLs when an event gets another showtime.  Include
        # the instant so every listed occurrence survives as a separate stable event.
        native_id = f"{url}|{start.isoformat()}"
        return self.event(
            title=title,
            start=start,
            url=url,
            place_raw=self.cfg.place,
            venue="Klub Kus",
            description=description[:500],
            image=urljoin(self.cfg.url, image["src"]) if image else None,
            native_id=native_id,
        )

    @staticmethod
    def _parse_start(value: str | None) -> datetime:
        if not value:
            raise ValueError("Klub Kus programme event has no datetime")
        # ``fromisoformat`` accepts a bare date too, but this listing promises an explicit show
        # time.  Treating a broken ``datetime=YYYY-MM-DD`` as midnight would silently invent one.
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?", value.strip()):
            raise ValueError(f"Klub Kus programme has no explicit valid time: {value!r}")
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError as exc:
            raise ValueError(f"Klub Kus programme has invalid datetime: {value!r}") from exc
        if parsed.tzinfo is not None:
            return parsed.astimezone(TZ)
        return parsed.replace(tzinfo=TZ)
