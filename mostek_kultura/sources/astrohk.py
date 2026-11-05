"""Public monthly programme of the Hradec Králové observatory and planetarium."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from ..dates import TZ
from ..model import Event
from .base import Source, clean, soup

_MONTHS = {
    "leden": 1, "únor": 2, "březen": 3, "duben": 4, "květen": 5, "červen": 6,
    "červenec": 7, "srpen": 8, "září": 9, "říjen": 10, "listopad": 11, "prosinec": 12,
}
_CURRENT = re.compile(r"AKTUÁLNÍ ČÍSLO\s*[-–]\s*(?P<month>\w+)\s+(?P<year>\d{4})", re.IGNORECASE)
_PDF = re.compile(r"(?:^|/)data/mesicnik/(?P<dir_year>\d{4})/Mesicnik-(?P<year>\d{4})-(?P<month>\d{2})\.pdf$", re.IGNORECASE)
_PROGRAM = re.compile(r"Program na\s+(?P<month>\w+)", re.IGNORECASE)
_EXPLICIT = re.compile(r"(?P<day>\d{1,2})\.\s*(?P<month>\d{1,2})\.\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*\|\s*(?P<title>.+)")
_WEEKLY = re.compile(r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*\|\s*(?P<title>.+)")
_RESTRICTION = re.compile(r"(?P<kind>pouze|nekoná se|neprobíhá|kromě)\s+(?P<day>\d{1,2})\.\s*(?P<month>\d{1,2})\.?(?:\s+(?P<year>\d{4}))?", re.IGNORECASE)
_WEEKDAYS = {"STŘEDY": 2, "PÁTKY": 4, "SOBOTY": 5}
_VENUE = "Hvězdárna a planetárium v Hradci Králové"


class AstrohkSource(Source):
    """Expand dated lectures and weekly public shows within a verified month."""

    def fetch(self, http) -> list[Event]:
        program_html = http.get_text(self.cfg.url)
        month_html = http.get_text(urljoin(self.cfg.url, "mesicnik.php"))
        return self.parse(program_html, month_html)

    def parse(self, program_html: str, month_html: str) -> list[Event]:
        doc = soup(program_html)
        listing = doc.select_one("#vse")
        if listing is None:
            raise ValueError("Astrohk public programme #vse missing")
        if not clean(listing.get_text(" ")) and not listing.select("button.faq, table"):
            return []

        year, month = self._verified_month(doc, month_html)
        events: list[Event] = []
        group = None
        restriction = ""
        saw_programme = False
        parsed_answers: set[int] = set()
        for node in listing.find_all(recursive=False):
            if node.name == "table":
                label = clean(node.get_text(" ")).upper()
                weekday = next((key for key in _WEEKDAYS if label == key or label.startswith(key + " ")), None)
                if weekday:
                    group = weekday
                    restriction = label[len(weekday):].strip()
                    self._restricted_days(year, month, _WEEKDAYS[weekday], restriction)
                    saw_programme = True
                elif label in {"PŘEDNÁŠKY", "KVÍZY"}:
                    group = label
                    restriction = ""
                    saw_programme = True
                elif label in {"PROGRAM PRO SKUPINY", "VÝSTAVY", "JAK ZAKOUPIT VSTUPENKY"} or label.startswith(("VSTUPNÉ NA PROGRAMY", "DRUH PROGRAMU", "ČLENOVÉ ASTRONOMICKÉ SPOLEČNOSTI")):
                    group = "IGNORE"
                else:
                    group = None
                continue
            if node.name == "div" and "odpoved" in node.get("class", []) and group not in {None, "IGNORE"} and id(node) not in parsed_answers:
                raise ValueError("Astrohk programme answer has no FAQ")
            if node.name != "button":
                continue
            if group == "IGNORE":
                continue
            if group is None:
                if re.match(r"^(?:\d{1,2}:\d{2}|\d{1,2}\.\s*\d{1,2}\.)", clean(node.get_text(" "))):
                    raise ValueError("Astrohk dated public item has an unknown section")
                continue
            if "faq" not in node.get("class", []):
                raise ValueError("Astrohk programme button has changed markup")
            answer = node.find_next_sibling()
            if answer is None or "odpoved" not in answer.get("class", []):
                raise ValueError("Astrohk programme FAQ has no answer")
            parsed_answers.add(id(answer))
            text = clean(node.get_text(" "))
            if group in {"PŘEDNÁŠKY", "KVÍZY"}:
                match = _EXPLICIT.fullmatch(text)
                if match is None:
                    raise ValueError(f"Astrohk lecture has no explicit date: {text!r}")
                if int(match.group("month")) != month:
                    raise ValueError("Astrohk lecture month differs from programme")
                starts = [self._datetime(year, month, int(match.group("day")), match)]
            else:
                match = _WEEKLY.fullmatch(text)
                if match is None:
                    raise ValueError(f"Astrohk weekly programme has no time: {text!r}")
                title, *qualifiers = [clean(part) for part in match.group("title").split("|")]
                days = self._restricted_days(year, month, _WEEKDAYS[group], " ".join([restriction, *qualifiers]))
                starts = [self._datetime(year, month, day, match) for day in days]
            title = clean(match.group("title").split("|")[0])
            if not title:
                raise ValueError("Astrohk programme item has no title")
            duration, description, image = self._answer(answer, text)
            category = self._category(title, group)
            for start in starts:
                events.append(self.event(
                    title=title,
                    start=start,
                    end=start + timedelta(minutes=duration) if duration else None,
                    url=self.cfg.page_url,
                    place_raw=self.cfg.place,
                    venue=_VENUE,
                    category=category,
                    native_category={"deti": "Pro děti", "prednaska": "Přednáška", "jine": "Jiné"}[category],
                    description=description,
                    image=image,
                    native_id=f"{title}|{start.isoformat()}",
                ))
        if not saw_programme:
            raise ValueError("Astrohk public programme sections missing")
        return events

    @staticmethod
    def _verified_month(doc, month_html: str) -> tuple[int, int]:
        issues = soup(month_html)
        dates = set()
        for link in issues.select("a[href]"):
            label = _CURRENT.fullmatch(clean(link.get_text(" ")))
            if label is None:
                continue
            pdf = _PDF.search(link["href"])
            name = label.group("month").lower()
            if pdf is None or name not in _MONTHS:
                raise ValueError("Astrohk current Měsíčník link malformed")
            year, month = int(label.group("year")), _MONTHS[name]
            if (int(pdf.group("dir_year")), int(pdf.group("year")), int(pdf.group("month"))) != (year, year, month):
                raise ValueError("Astrohk Měsíčník label and PDF date differ")
            dates.add((year, month))
        if len(dates) != 1:
            raise ValueError("Astrohk current Měsíčník date missing or ambiguous")
        year, month = dates.pop()
        headings = {
            _MONTHS[match.group("month").lower()]
            for tag in doc.select("b")
            if (match := _PROGRAM.fullmatch(clean(tag.get_text(" "))))
            and match.group("month").lower() in _MONTHS
        }
        if headings != {month}:
            raise ValueError("Astrohk programme and current Měsíčník month differ")
        return year, month

    @staticmethod
    def _restricted_days(year: int, month: int, weekday: int, text: str) -> list[int]:
        normalized = clean(text).lower()
        normalized = normalized.replace("pouze za jasné oblohy", "")
        normalized = re.sub(r"pořad vhodný pro diváky ve věku od \d+(?: do \d+)? let", "", normalized)
        matches = list(_RESTRICTION.finditer(normalized))
        remainder = normalized
        for match in matches:
            remainder = remainder.replace(match.group(0), "")
        if re.search(r"\w", remainder):
            raise ValueError(f"Astrohk unsupported calendar restriction: {text!r}")
        if sum(match.group("kind").lower() == "pouze" for match in matches) > 1:
            raise ValueError(f"Astrohk ambiguous exclusive days: {text!r}")
        days = [day for day in range(1, calendar.monthrange(year, month)[1] + 1)
                if date(year, month, day).weekday() == weekday]
        for match in matches:
            day, restricted_month = int(match.group("day")), int(match.group("month"))
            restricted_year = int(match.group("year")) if match.group("year") else year
            try:
                date(restricted_year, restricted_month, day)
            except ValueError as exc:
                raise ValueError(f"Astrohk invalid restricted day: {text!r}") from exc
            if match.group("kind").lower() == "pouze":
                days = [day] if (restricted_year, restricted_month) == (year, month) and day in days else []
            elif (restricted_year, restricted_month) == (year, month):
                days = [candidate for candidate in days if candidate != day]
        return days

    @staticmethod
    def _datetime(year: int, month: int, day: int, match) -> datetime:
        try:
            return datetime(year, month, day, int(match.group("hour")), int(match.group("minute")), tzinfo=TZ)
        except ValueError as exc:
            raise ValueError("Astrohk programme contains invalid date or time") from exc

    def _answer(self, answer, faq_text: str) -> tuple[int | None, str, str | None]:
        duration = None
        description_parts = []
        for row in answer.select("tr"):
            icons = [img.get("src", "") for img in row.select("img")]
            value = clean(row.get_text(" "))
            if any(src.endswith("/time.png") for src in icons):
                match = re.fullmatch(r"(\d{1,3})\s+minut(?:a|y)?", value)
                if match is None:
                    raise ValueError("Astrohk programme duration malformed")
                duration = int(match.group(1))
            elif any(src.endswith("/information.png") for src in icons) or (not icons and value):
                description_parts.append(value)
        if "pouze za jasné oblohy" in faq_text.lower():
            description_parts.insert(0, "Koná se pouze za jasné oblohy.")
        description = clean(" ".join(description_parts))[:500]
        image_tag = next((img for img in answer.select("img[src]")
                          if "/icons/" not in img["src"] and not img["src"].startswith("data:")), None)
        image = urljoin(self.cfg.url, image_tag["src"]) if image_tag else None
        return duration, description, image

    @staticmethod
    def _category(title: str, group: str) -> str:
        if group in {"PŘEDNÁŠKY", "KVÍZY"}:
            return "prednaska"
        if "pro děti" in title.lower() or "pohádk" in title.lower():
            return "deti"
        if "pozorování" in title.lower():
            return "jine"
        return "prednaska"
