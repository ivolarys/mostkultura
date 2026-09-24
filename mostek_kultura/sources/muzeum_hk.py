"""JEvents monthly calendar and event details at muzeumhk.cz."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from ..dates import TZ, today
from ..model import Event
from .base import Source, clean, soup

_DETAIL = re.compile(r"/program/kalendar-akci/(\d+)/-/[^/]+\.html$")
_DATE = re.compile(r"\b(\d{1,2})\.\s*([a-zá-ž]+)\s+(\d{4})\b", re.IGNORECASE)
_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_COLOR = re.compile(r"border-(?:left|color):?\s*(?:\d+px\s+solid\s+)?(#[0-9a-f]{3,8})", re.IGNORECASE)
_MONTHS = {
    "leden": 1, "ledna": 1, "únor": 2, "února": 2, "březen": 3, "března": 3,
    "duben": 4, "dubna": 4, "květen": 5, "května": 5, "červen": 6, "června": 6,
    "červenec": 7, "července": 7, "srpen": 8, "srpna": 8, "září": 9,
    "říjen": 10, "října": 10, "listopad": 11, "listopadu": 11,
    "prosinec": 12, "prosince": 12,
}
_MAIN = "Muzeum východních Čech v Hradci Králové"
_ARCHA = "Muzeum východních Čech - budova ARCHA"


class MuzeumHkSource(Source):
    def month_urls(self, ref: date | None = None) -> list[str]:
        ref = ref or today()
        months = max(1, int(self.cfg.extra.get("months", 3)))
        root = self.cfg.url.rstrip("/").removesuffix("/kalendar-akci")
        urls = []
        for offset in range(months):
            year, month_index = divmod(ref.year * 12 + ref.month - 1 + offset, 12)
            urls.append(f"{root}/kalendar-akci/udalostimesice/{year}/{month_index + 1}/-.html")
        return urls

    def fetch(self, http) -> list[Event]:
        links: dict[str, tuple[str, str | None]] = {}
        for url in self.month_urls():
            links.update(self.parse_month(http.get_text(url), url))
        out: list[Event] = []
        for native_id, (url, category) in links.items():
            if category == "Pro školy":
                continue
            event = self.parse_detail(http.get_text(url), url, native_id, category)
            if event:
                out.append(event)
        return out

    def parse_month(self, html: str, url: str) -> dict[str, tuple[str, str | None]]:
        doc = soup(html)
        body = doc.select_one("#jevents_body")
        if body is None or body.select_one(".cal_table") is None:
            raise ValueError(f"Museum monthly calendar markup missing: {url}")
        categories: dict[str, str] = {}
        for legend in body.select(".event_legend_item.activechildcat"):
            color = _COLOR.search(legend.get("style", ""))
            label = legend.select_one(".event_legend_name")
            if color and label:
                categories[color.group(1).lower()] = clean(label.get_text(" "))
        links: dict[str, tuple[str, str | None]] = {}
        for link in body.select(".cal_table a.cal_titlelink[href]"):
            href = link.get("href", "")
            match = _DETAIL.search(href)
            if not match:
                raise ValueError(f"Museum monthly calendar has malformed event link: {url}")
            cell = link.find_parent(class_="month_cell_st")
            color = _COLOR.search(cell.get("style", "")) if cell else None
            category = categories.get(color.group(1).lower()) if color else None
            links[match.group(1)] = (urljoin(url, href), category)
        return links

    def parse_detail(self, html: str, url: str, native_id: str, calendar_category: str | None = None) -> Event | None:
        doc = soup(html)
        body = doc.select_one("#jevents_body")
        title_el = body.select_one(".jev_evdt_title") if body else None
        summary = body.select_one(".jev_evdt_summary") if body else None
        if not title_el or not summary:
            raise ValueError(f"Museum event detail markup missing: {url}")
        title = clean(title_el.get_text(" "))
        if not title:
            raise ValueError(f"Museum event title missing: {url}")
        # Permanent displays are not dated cultural events even when JEvents gives them a
        # synthetic multi-year range.  Keep temporary exhibitions.
        if ("stálá expozice" in title.casefold() or "stale expozice" in title.casefold()
                or calendar_category == "Pro školy"):
            return None
        start, end, all_day = self.parse_summary(summary.get_text(" "))
        desc_el = body.select_one(".jev_evdt_desc")
        desc = clean(desc_el.get_text(" ")) if desc_el else ""
        loc_el = body.select_one(".jev_evdt_location")
        place_raw, venue = self.parse_location(loc_el, title, desc)
        image = None
        if desc_el:
            for img in desc_el.select("img"):
                candidate = img.get("data-src") or img.get("src")
                if candidate and not candidate.startswith("data:"):
                    image = urljoin(url, candidate)
                    break
        native_category = "Výstava" if calendar_category and calendar_category.startswith("Výstavy") else None
        if title.casefold().startswith("přednáška"):
            native_category = "Přednáška"
        return self.event(
            title=title, start=start, end=end, all_day=all_day, url=url,
            place_raw=place_raw, venue=venue, native_category=native_category,
            description=desc[:500], image=image, native_id=native_id,
        )

    @staticmethod
    def parse_summary(raw: str) -> tuple[datetime, datetime | None, bool]:
        text = clean(raw)
        dates = list(_DATE.finditer(text))
        if not dates or len(dates) > 2:
            raise ValueError(f"Museum event has no valid explicit date: {text}")

        def parse_day(match) -> date:
            month = _MONTHS.get(match.group(2).casefold())
            if month is None:
                raise ValueError(f"Unknown Czech month in museum event: {text}")
            return date(int(match.group(3)), month, int(match.group(1)))

        first = parse_day(dates[0])
        second = parse_day(dates[1]) if len(dates) == 2 else None
        first_times = [tuple(map(int, m.groups())) for m in _TIME.finditer(text[dates[0].end():dates[1].start() if second else None])]
        second_times = [tuple(map(int, m.groups())) for m in _TIME.finditer(text[dates[1].end():])] if second else []
        all_day = not first_times
        start = datetime(first.year, first.month, first.day, *(first_times[0] if first_times else (0, 0)), tzinfo=TZ)
        end = None
        if second:
            if second < first:
                raise ValueError(f"Museum event ends before it starts: {text}")
            time = second_times[0] if second_times else (23, 59)
            end = datetime(second.year, second.month, second.day, *time, tzinfo=TZ)
        elif len(first_times) > 1:
            end = datetime(first.year, first.month, first.day, *first_times[1], tzinfo=TZ)
            if end <= start:
                end += timedelta(days=1)
        if end and end < start:
            raise ValueError(f"Museum event has invalid end: {text}")
        return start, end, all_day

    @staticmethod
    def parse_location(loc_el, title: str, desc: str) -> tuple[str, str]:
        if loc_el:
            lines = [clean(line) for line in loc_el.get_text("\n").splitlines()]
            lines = [line for line in lines if line and line != "Místo"]
            if lines:
                venue = lines[0]
                if any(line == "Chlum" for line in lines):
                    return "Chlum", venue
                in_hradec = any(line == "Hradec Králové" for line in lines)
                if not in_hradec:
                    # A named venue in another municipality must not inherit the museum's city.
                    return lines[2] if len(lines) > 2 else venue, venue
                if "gayer" in venue.casefold():
                    return "Hradec Králové", "Hlavní odborné pracoviště Gayerova kasárna"
                if "archa" in venue.casefold():
                    return "Hradec Králové", _ARCHA
                if "muze" in venue.casefold() or "kotěr" in venue.casefold():
                    return "Hradec Králové", _MAIN
                return "Hradec Králové", venue
        if "archa" in f"{title} {desc}".casefold():
            return "Hradec Králové", _ARCHA
        if "gayer" in f"{title} {desc}".casefold():
            return "Hradec Králové", "Hlavní odborné pracoviště Gayerova kasárna"
        return "Hradec Králové", _MAIN
