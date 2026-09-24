"""Calendar and explicitly dated exhibitions of galeriehk.cz."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from urllib.parse import urljoin

from ..dates import TZ, today
from ..model import Event
from .base import Source, clean, soup

_DAY = re.compile(r"\b(\d{1,2})/(\d{1,2})\b")
_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_RANGE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\s*[–—-]\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
_VENUE = "Galerie moderního umění v Hradci Králové"


def _full_year(raw: str) -> int:
    year = int(raw)
    return 2000 + year if len(raw) == 2 else year


def _month_shift(day: date, offset: int) -> tuple[int, int]:
    index = day.year * 12 + day.month - 1 + offset
    return index // 12, index % 12 + 1


class GalerieHkSource(Source):
    def fetch(self, http) -> list[Event]:
        out: list[Event] = []
        ajax_url = urljoin(self.cfg.url, "/wp-admin/admin-ajax.php")
        for offset in range(3):
            year, month = _month_shift(today(), offset)
            raw = http.post_text(ajax_url, {
                "mesic": f"{month:02d}", "rok": year, "action": "get_all_month_program",
            })
            out.extend(self.parse_calendar(raw, year=year, month=month))
        for path in ("/soucasne-vystavy/", "/budouci-vystavy/"):
            out.extend(self.parse_exhibitions(http.get_text(urljoin(self.cfg.url, path))))
        # Source cards occasionally repeat a programme entry; the same workshop
        # on a different date is intentionally a separate event.
        seen: set[tuple[str, datetime]] = set()
        unique: list[Event] = []
        for event in out:
            key = (event.url, event.start)
            if key not in seen:
                seen.add(key)
                unique.append(event)
        return unique

    def parse_calendar(self, raw: str, *, year: int, month: int) -> list[Event]:
        if not raw.strip():
            raise ValueError("empty gallery calendar response")
        try:
            html = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid gallery calendar response") from exc
        if not isinstance(html, str):
            raise ValueError("invalid gallery calendar payload")  # noqa: TRY004
        cards = soup(html).select(".program-item")
        if not cards:
            if not html.strip() or "není žádný program" in html.lower():
                return []
            raise ValueError("gallery calendar markup missing: .program-item")
        out: list[Event] = []
        for card in cards:
            out.extend(self._calendar_card(card, year, month))
        return out

    def _calendar_card(self, card, year: int, month: int) -> list[Event]:
        date_el = card.select_one(".date-label")
        title_el = card.select_one("h3 a[href]")
        if date_el is None or title_el is None:
            raise ValueError("malformed gallery calendar card")
        match = _DAY.search(clean(date_el.get_text(" ")))
        if not match:
            raise ValueError("calendar card lacks explicit day and month")
        day, card_month = map(int, match.groups())
        if card_month != month:
            raise ValueError("calendar card month differs from requested month")
        event_date = date(year, month, day)
        title = clean(title_el.get_text(" "))
        if not title:
            raise ValueError("calendar card lacks title")
        cols = card.find_all("div", recursive=False)
        if len(cols) < 3:
            raise ValueError("calendar card lacks schedule or description column")
        schedule = clean(cols[1].get_text(" ")) if len(cols) > 1 else ""
        clock_text = schedule.split("|", 1)[0]
        times = [(int(hour), int(minute)) for hour, minute in _TIME.findall(clock_text)]
        if any(hour > 23 or minute > 59 for hour, minute in times):
            raise ValueError("invalid programme time")
        separate_sessions = bool(re.search(r"\d{1,2}:\d{2}\s*&\s*\d{1,2}:\d{2}", clock_text))
        body = cols[2]
        description = clean(body.get_text(" ").replace(title, "", 1))[:500]
        url = urljoin(self.cfg.url, title_el["href"])
        lowered = title.casefold()
        native_category = (
            "Koncert" if "dj set" in lowered else
            "Workshop" if "workshop" in lowered or "ateliér" in lowered else
            "Přednáška" if "umění zblízka" in lowered or "edu naproti" in lowered else
            "Výstava" if "exhibition" in lowered or "dernisáž" in lowered else
            "Jiné"
        )
        if separate_sessions and len(times) != 2:
            raise ValueError("invalid programme session list")
        if len(times) > 2:
            raise ValueError("unsupported programme time format")
        starts = times if separate_sessions else times[:1] or [None]
        out = []
        for slot in starts:
            start = datetime.combine(event_date, datetime.min.time(), TZ)
            if slot:
                start = start.replace(hour=slot[0], minute=slot[1])
            end = None
            if not separate_sessions and len(times) == 2:
                end = start.replace(hour=times[1][0], minute=times[1][1])
                if end <= start:
                    raise ValueError("invalid programme time range")
            out.append(self.event(
                title=title, start=start, end=end, all_day=not times,
                url=url, venue=_VENUE, description=description, native_category=native_category,
                native_id=f"{url}|{event_date.isoformat()}|{start.time().isoformat()}",
            ))
        return out

    def parse_exhibitions(self, html: str) -> list[Event]:
        out: list[Event] = []
        section = soup(html).select_one("section.vystavy")
        if section is None:
            raise ValueError("gallery exhibitions markup missing: section.vystavy")
        for heading in section.select("h3.inherit-h2"):
            card = heading.parent
            if card is None:
                continue
            section = card.select_one("h2")
            if section and "stálá expozice" in clean(section.get_text(" ")).lower():
                continue
            link = heading.select_one("a[href]")
            if link is None:
                continue
            text = clean(link.get_text(" "))
            match = _RANGE.search(text)
            if not match:
                continue
            d1, m1, y1, d2, m2, y2 = match.groups()
            try:
                first = date(_full_year(y1), int(m1), int(d1))
                last = date(_full_year(y2), int(m2), int(d2))
            except ValueError:
                continue
            if last < first:
                continue
            title = clean(text[:match.start()])
            if not title:
                continue
            url = urljoin(self.cfg.url, link["href"])
            detail = card.select_one(".vystavy-mobile")
            image = detail.select_one("img[src]") if detail else None
            description = clean(detail.select_one("p").get_text(" "))[:500] if detail and detail.select_one("p") else ""
            out.append(self.event(
                title=title, start=datetime.combine(first, datetime.min.time(), TZ),
                end=datetime.combine(last, datetime.max.time().replace(microsecond=0), TZ),
                all_day=True, url=url, venue=_VENUE, native_category="Výstava",
                description=description, image=urljoin(self.cfg.url, image["src"]) if image else None,
                native_id=url,
            ))
        return out
