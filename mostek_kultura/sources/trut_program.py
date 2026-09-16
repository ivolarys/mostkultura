"""Trut, z. s. programme at trut.cz/akce/.

The listing is a small server-rendered set of ``article.card`` items.  Its cards
only carry a date, so each detail is required: it holds the explicit event date,
place and (when published) the time range.  Publication/update dates must never
be mistaken for the event date.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from ..dates import parse_cz
from ..model import Event
from .base import Source, clean, soup

_EXPLICIT_YEAR = re.compile(r"\b\d{1,2}\.\s*(?:\d{1,2}\.|[a-zá-ž]+)\s*\d{4}\b", re.IGNORECASE)


class TrutProgramSource(Source):
    def fetch(self, http) -> list[Event]:
        items = self.parse_listing(http.get_text(self.cfg.url))
        events: list[Event] = []
        for title, url in items:
            # A failed or structurally invalid detail makes the whole source fail.  Reporting a
            # healthy partial programme would otherwise overwrite the last known good result.
            events.append(self.parse_detail(http.get_text(url), title, url))
        return events

    def parse_listing(self, html: str) -> list[tuple[str, str]]:
        container = soup(html).select_one("section.section .container")
        if not container or clean(container.select_one("h1").get_text() if container.select_one("h1") else "") != "Akce":
            raise ValueError("Trut listing markup missing section.section .container > h1 Akce")
        cards = container.select("article.card")
        if not cards:
            return []
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for card in cards:
            link = card.select_one("h3 a[href]")
            if not link:
                raise ValueError("Trut listing contains a malformed event card")
            title = clean(link.get_text())
            url = urljoin(self.cfg.url, link["href"])
            if not title:
                raise ValueError("Trut listing contains an event card without a title")
            if url not in seen:
                seen.add(url)
                out.append((title, url))
        if not out:
            raise ValueError("Trut listing contains cards but no valid event links")
        return out

    def parse_detail(self, html: str, listed_title: str, url: str) -> Event:
        container = soup(html).select_one("section.section .container")
        title_el = container.select_one("h1") if container else None
        title = clean(title_el.get_text()) if title_el else ""
        if not container or not title:
            raise ValueError(f"Trut detail markup missing title: {url}")
        date_text = self._metadata(container, "Datum:")
        if not date_text or not _EXPLICIT_YEAR.search(date_text):
            raise ValueError(f"Trut detail has no explicit event date: {url}")
        parsed = parse_cz(date_text)
        if not parsed:
            raise ValueError(f"Trut detail has invalid event date: {url}")
        start, end, all_day = parsed
        place = self._metadata(container, "Místo:") or self.cfg.place

        description = ""
        # Only a prose paragraph whose date agrees with the metadata can add a time.  This keeps
        # e.g. "Datum aktualizace" and unrelated historical dates out of the schedule.
        matching_date_prose: list[str] = []
        for paragraph in container.find_all("p"):
            text = clean(paragraph.get_text(" "))
            if self._is_metadata_paragraph(paragraph) or text.startswith("Datum aktualizace:"):
                continue
            candidate = parse_cz(text) if _EXPLICIT_YEAR.search(text) else None
            if candidate and candidate[0].date() == start.date():
                matching_date_prose.append(text)
                c_start, c_end, c_all_day = candidate
                if not c_all_day:
                    start, end, all_day = c_start, c_end, c_all_day
                    description = text
                    break
        if not description and matching_date_prose:
            description = matching_date_prose[0]
        if not description:
            for paragraph in container.find_all("p"):
                text = clean(paragraph.get_text(" "))
                if (text and not self._is_metadata_paragraph(paragraph)
                        and not text.startswith("Datum aktualizace:")
                        and not paragraph.select_one("a[href], button")):
                    description = text
                    break

        # "Trutnov" names the municipality while this event occurs across several reading sites;
        # storing it as a venue would wrongly suggest a single address.
        venue = place if place and place.casefold() != (self.cfg.place or "").casefold() else None
        return self.event(
            title=title or listed_title,
            start=start,
            end=end,
            all_day=all_day,
            url=url,
            place_raw=place,
            venue=venue,
            description=description[:500],
            native_id=url,
        )

    @staticmethod
    def _metadata(container, label: str) -> str | None:
        for strong in container.select("p > strong"):
            if clean(strong.get_text()) == label:
                text = clean(strong.parent.get_text(" "))
                return clean(re.sub(rf"^\s*{re.escape(label)}\s*", "", text)) or None
        return None

    @staticmethod
    def _is_metadata_paragraph(paragraph) -> bool:
        strong = paragraph.select_one(":scope > strong")
        return bool(strong and clean(strong.get_text()) in {"Datum:", "Místo:"})
