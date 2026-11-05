"""Dated concert blocks from the Jazzinec festival homepage."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from ..dates import TZ
from ..model import Event
from .base import Source, clean, soup

_DATE = re.compile(r"(?P<day>\d{1,2})/(?P<month>\d{1,2})")
_TIME = re.compile(r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?")
_SLIDER_ALT = re.compile(r"jazzinec-(\d{4})-web-slider", re.IGNORECASE)
_SLIDER_SRC = re.compile(r"/Foto/(\d{4})/SliderFoto/", re.IGNORECASE)


class JazzinecSource(Source):
    def fetch(self, http) -> list[Event]:
        return self.parse(http.get_text(self.cfg.url))

    def parse(self, html: str) -> list[Event]:
        doc = soup(html)
        program = doc.select_one(".program-cont .container.program")
        if program is None:
            raise ValueError("Jazzinec programme container missing")
        date_tags = program.select(".program-date")
        if not date_tags:
            if program.select(".program-radek, .program-time, .program-misto, .col-xs-3, .col-xs-9"):
                raise ValueError("Jazzinec programme contains a block without a date")
            return []
        if len(program.select(".col-xs-3")) != len(date_tags) or len(program.select(".col-xs-9")) != len(date_tags):
            raise ValueError("Jazzinec programme has an undated or incomplete concert block")

        years = set()
        for image in doc.select(".slider-cont .banner-rotator img[alt][src]"):
            alt = _SLIDER_ALT.search(image.get("alt", ""))
            src = _SLIDER_SRC.search(image.get("src", ""))
            if alt and src:
                if alt.group(1) != src.group(1):
                    raise ValueError("Jazzinec slider edition year conflicts with image path")
                years.add(int(alt.group(1)))
        if len(years) != 1:
            raise ValueError("Jazzinec slider edition year missing or ambiguous")
        year = years.pop()

        images = {}
        for link in doc.select("#ucinkujici1 a[href]"):
            image = link.select_one("img[src]")
            if image:
                images[urljoin(self.cfg.url, link["href"])] = urljoin(self.cfg.url, image["src"])

        events = []
        parsed_rows = 0
        for date_tag in date_tags:
            date_column = date_tag.parent
            if "col-xs-3" not in date_column.get("class", []):
                raise ValueError("Jazzinec programme date is outside its date column")
            detail_column = date_column.find_next_sibling("div")
            if detail_column is None or "col-xs-9" not in detail_column.get("class", []):
                raise ValueError("Jazzinec programme date has no concert block")

            date_text = clean(date_tag.get_text(" "))
            time_tag = date_column.select_one(".program-time")
            time_text = clean(time_tag.get_text(" ")) if time_tag else ""
            date_match = _DATE.fullmatch(date_text)
            time_match = _TIME.fullmatch(time_text)
            if not date_match or not time_match:
                raise ValueError(f"Jazzinec programme date or time invalid: {date_text!r}, {time_text!r}")
            try:
                start = datetime(
                    year, int(date_match.group("month")), int(date_match.group("day")),
                    int(time_match.group("hour")), int(time_match.group("minute") or 0),
                    tzinfo=TZ,
                )
            except ValueError as exc:
                raise ValueError(f"Jazzinec programme date or time invalid: {date_text!r}, {time_text!r}") from exc

            venue_tag = detail_column.select_one(".program-misto")
            venue = clean(venue_tag.get_text(" ")) if venue_tag else ""
            performers = []
            urls = []
            for row in detail_column.select(".program-radek"):
                link = row.select_one("a[href]")
                if link is None or not clean(link.get_text(" ")) or not clean(link.get("href")):
                    raise ValueError("Jazzinec programme concert row lacks performer or link")
                performers.append(clean(link.get_text(" ")))
                urls.append(urljoin(self.cfg.url, link["href"]))
                parsed_rows += 1
            if not performers or not venue:
                raise ValueError("Jazzinec programme concert block lacks performer or venue")

            url = urls[0]
            events.append(self.event(
                title=" + ".join(performers),
                start=start,
                url=url,
                place_raw=self.cfg.place,
                venue="UFFO" if venue.casefold() == "uffo" else venue,
                native_category="Koncert",
                image=next((images[item] for item in urls if item in images), None),
                native_id=f"{url}|{start.isoformat()}",
            ))
        if parsed_rows != len(program.select(".program-radek")):
            raise ValueError("Jazzinec programme contains an unpaired concert row")
        return events
