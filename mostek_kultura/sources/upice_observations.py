"""Regular public evening observations at Hvězdárna v Úpici."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

from ..dates import TZ
from ..model import Event
from .base import Source, clean, soup

_API = "https://www.hvezdarnavupici.cz/?rest_route=/wp/v2/posts&per_page=20"
_HOURS = "https://www.hvezdarnavupici.cz/?page_id=36"
_MONTHS = {
    "lednu": 1, "únoru": 2, "březnu": 3, "dubnu": 4, "květnu": 5, "červnu": 6,
    "červenci": 7, "srpnu": 8, "září": 9, "říjnu": 10, "listopadu": 11, "prosinci": 12,
}
_MONTH_LABELS = {
    "leden": 1, "únor": 2, "březen": 3, "duben": 4, "květen": 5, "červen": 6,
    "červenec": 7, "srpen": 8, "září": 9, "říjen": 10, "listopad": 11, "prosinec": 12,
}
_ARTICLE = re.compile(
    r"Obloha(?:\s*\(a akce nejen na úpické hvězdárně\)|\s+a akce(?: nejen)? na úpické hvězdárně)"
    r"\s+v\s+(?P<month>\w+)\s+(?P<year>\d{4})",
    re.IGNORECASE,
)
_PERIOD = re.compile(
    r"V\s+(?P<month>\w+)\b.*?začínají večerní pozorování noční oblohy"
    r".*?pro veřejnost v\s+(?P<start>\d{1,2})\s+hodin(?:y|u)?\s+a končí ve\s+"
    r"(?P<end>\d{1,2})\s+hodin(?:y|u)?",
    re.IGNORECASE,
)
_INTERVAL = re.compile(r"(?P<start>\d{1,2}):(?P<start_min>\d{2})\s*[-–]\s*(?P<end>\d{1,2}):(?P<end_min>\d{2})")
_START = re.compile(r"\d{1,2}:\d{2}")
_WEEKDAYS = ("pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle a svátky")


class UpiceObservationsSource(Source):
    """Combine an explicit monthly article with the published opening-hours table."""

    def fetch(self, http) -> list[Event]:
        posts = http.get_json(_API)
        hours_html = http.get_text(_HOURS)
        return self.parse(posts, hours_html)

    def parse(self, posts: list[dict], hours_html: str) -> list[Event]:
        article, year, month = self._current_article(posts)
        if month in {7, 8}:
            raise ValueError("Úpice summer expedition has no verified date range")
        start_hour, end_hour = self._article_hours(article, month, year)
        hours_by_weekday, table_start = self._hours_table(hours_html, month)
        if table_start != start_hour:
            raise ValueError("Úpice article and opening-hours table disagree on observation start")

        events: list[Event] = []
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            current = date(year, month, day)
            weekday = current.weekday()
            if weekday == 6 or current in _czech_holidays(year):
                continue
            intervals = hours_by_weekday[weekday]
            if not any(open_hour <= start_hour and end_hour <= close_hour
                       for open_hour, close_hour in intervals):
                raise ValueError(f"Úpice hours do not cover evening observations on {current}")
            start = datetime(year, month, day, start_hour, tzinfo=TZ)
            end = (datetime(year, month, day, 0, tzinfo=TZ) + timedelta(days=1)
                   if end_hour == 24 else datetime(year, month, day, end_hour, tzinfo=TZ))
            events.append(self.event(
                title="Večerní pozorování oblohy",
                start=start,
                end=end,
                url=article["link"],
                place_raw=self.cfg.place,
                venue="Hvězdárna v Úpici",
                category="jine",
                native_category="Pozorování",
                description="Pozorování noční oblohy dalekohledy se koná pouze za jasného počasí.",
                native_id=start.isoformat(),
            ))
        return events

    @staticmethod
    def _current_article(posts: list[dict]) -> tuple[dict, int, int]:
        if not isinstance(posts, list):
            raise ValueError("Úpice WordPress posts response malformed")  # noqa: TRY004
        candidates = []
        for post in posts:
            if not isinstance(post, dict) or not isinstance(post.get("title"), dict):
                raise ValueError("Úpice WordPress post malformed")  # noqa: TRY004
            title = clean(soup(post["title"].get("rendered", "")).get_text(" "))
            match = _ARTICLE.fullmatch(title)
            if match is None:
                continue
            month_name = match.group("month").lower()
            if month_name not in _MONTHS:
                raise ValueError(f"Úpice article has unknown month: {title!r}")
            if not post.get("link") or not post.get("date") or not isinstance(post.get("content"), dict):
                raise ValueError("Úpice monthly article lacks link, date, or content")
            candidates.append((post["date"], post, int(match.group("year")), _MONTHS[month_name]))
        if not candidates:
            raise ValueError("Úpice current monthly sky article missing")
        _, article, year, month = max(candidates, key=lambda candidate: candidate[0])
        return article, year, month

    @staticmethod
    def _article_hours(article: dict, month: int, year: int) -> tuple[int, int]:
        body = soup(article["content"].get("rendered", ""))
        heading = next((p for p in body.select("p")
                        if clean(p.get_text(" ")).lower().rstrip(":") == "začátky večerních pozorování"), None)
        if heading is None:
            raise ValueError("Úpice monthly article lacks evening observations section")
        paragraph = heading.find_next_sibling("p")
        if paragraph is None:
            raise ValueError("Úpice monthly article lacks observation hours")
        text = clean(paragraph.get_text(" "))
        match = _PERIOD.search(text)
        if match is None or _MONTHS.get(match.group("month").lower()) != month:
            raise ValueError("Úpice monthly article has no matching explicit observation period")
        start, end = int(match.group("start")), int(match.group("end"))
        if not (0 <= start < end <= 24):
            raise ValueError("Úpice monthly article observation hours invalid")
        full_text = clean(body.get_text(" ")).lower()
        # The article may discuss astronomical conditions, but an unparsed closure or
        # expedition must never turn into invented public observation dates.
        if re.search(r"uzavřen|zavřen|zavřeno|mimo provoz|expedic|omezen", full_text):
            raise ValueError("Úpice article mentions an unparsed opening restriction")
        for cancellation in re.finditer(r"nekoná\w*|neprobíhá\w*|neuskuteční\w*", full_text):
            context = full_text[max(0, cancellation.start() - 130):cancellation.start()]
            match_holiday = re.search(r"svátku?\s+(\d{1,2})\.\s*(\w+)", context)
            nearby_observations = ("večerní pozorování" in context
                                   or "večerní pozorování" in full_text[cancellation.start():cancellation.start() + 40])
            if match_holiday is None or not nearby_observations:
                raise ValueError("Úpice article mentions an unparsed observation cancellation")
            month_name = match_holiday.group(2)
            if (_MONTHS.get(month_name) or _MONTH_LABELS.get(month_name)) != month or date(year, month, int(match_holiday.group(1))) not in _czech_holidays(year):
                raise ValueError("Úpice article cancellation is not a verified public holiday")
        return start, end

    @staticmethod
    def _hours_table(html: str, month: int) -> tuple[list[list[tuple[int, int]]], int]:
        tables = soup(html).select("table.cla-text")
        if len(tables) != 1:
            raise ValueError("Úpice opening-hours table missing or ambiguous")
        rows = tables[0].select("tr")
        if not rows:
            raise ValueError("Úpice opening-hours table empty")
        header = [clean(cell.get_text(" ")).lower() for cell in rows[0].find_all(["td", "th"], recursive=False)]
        if len(header) != 10 or tuple(header[1:8]) != _WEEKDAYS or header[9] != "začátky večerních pozorování":
            raise ValueError("Úpice opening-hours table header changed")
        matching = []
        for row in rows[1:]:
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) != 10:
                raise ValueError("Úpice opening-hours table row malformed")
            label = clean(cells[0].get_text(" ")).lower()
            month_names = re.findall(r"[a-zá-ž]+", label)
            months = {_MONTH_LABELS[name] for name in month_names if name in _MONTH_LABELS}
            if "až" in month_names and len(months) == 2:
                first, last = sorted(months)
                months = set(range(first, last + 1))
            if month in months:
                matching.append(cells)
        if len(matching) != 1:
            raise ValueError("Úpice opening-hours month missing or ambiguous")
        cells = matching[0]
        starts = clean(cells[9].get_text(" "))
        if not _START.fullmatch(starts):
            raise ValueError("Úpice observation start in table malformed")
        hour, minute = map(int, starts.split(":"))
        if minute != 0:
            raise ValueError("Úpice table start has unsupported minutes")
        intervals = []
        for cell in cells[1:8]:
            value = clean(cell.get_text(" "))
            found = list(_INTERVAL.finditer(value))
            spans = [(int(m.group("start")), int(m.group("end")))
                     for m in found
                     if m.group("start_min") == "00" and m.group("end_min") == "00"]
            if not spans or len(spans) != len(found) or _INTERVAL.sub("", value).strip():
                raise ValueError("Úpice opening-hours weekday cell malformed")
            intervals.append(spans)
        return intervals, hour


def _czech_holidays(year: int) -> set[date]:
    fixed = ((1, 1), (5, 1), (5, 8), (7, 5), (7, 6), (9, 28),
             (10, 28), (11, 17), (12, 24), (12, 25), (12, 26))
    holidays = {date(year, month, day) for month, day in fixed}
    # Gregorian computus for Easter Sunday; Good Friday and Easter Monday are holidays.
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    easter_month, easter_day = divmod(h + l - 7 * m + 114, 31)
    easter = date(year, easter_month, easter_day + 1)
    holidays.update({easter - timedelta(days=2), easter + timedelta(days=1)})
    return holidays
