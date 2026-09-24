"""Dated Artičok event posts from its WordPress Akce category."""

from __future__ import annotations

import re
from datetime import datetime
from html import unescape
from urllib.parse import urljoin, urlsplit

from ..dates import MONTHS, TZ
from ..model import Event
from .base import Source, clean, soup

_MONTH_PATTERN = "|".join(sorted(map(re.escape, MONTHS), key=len, reverse=True))
_DATE = re.compile(
    r"(?<!\d)(?P<day>\d{1,2})\s*\.\s*"
    rf"(?P<month>1[0-2]|0?[1-9]|{_MONTH_PATTERN})(?!\w)"
    r"(?:\s*\.?\s*(?P<year>\d{4})(?!\d))?\s*\.?",
    re.IGNORECASE,
)
_TIME = re.compile(
    r"^\s*(?:[-–—]\s*)?(?P<hour>\d{1,2})"
    r"(?:(?:\s*[:.]\s*(?P<minute>\d{2}))|(?:\s*\.?(?=\s*hodin\b)))?"
    r"(?P<suffix>\s*\.?\s*hodin\b)?",
    re.IGNORECASE,
)
_RANGE = re.compile(r"^\s*[-–—]\s*")
_VENUE = re.compile(r"\bpřed\s+vinotéku\s+IN\s+VINO\b", re.IGNORECASE)
_PAGE_SIZE = 100
_MAX_PAGES = 5


class ArticokSource(Source):
    def fetch(self, http) -> list[Event]:
        base = f"{urlsplit(self.cfg.url).scheme}://{urlsplit(self.cfg.url).netloc}"
        api = f"{base}/wp-json/wp/v2/posts?categories=1&per_page={_PAGE_SIZE}&_embed=1"
        posts = []
        for page in range(_MAX_PAGES):
            batch = http.get_json(f"{api}&offset={page * _PAGE_SIZE}")
            if not isinstance(batch, list) or not all(isinstance(post, dict) for post in batch):
                raise ValueError("Artičok API returned an invalid posts list")
            posts.extend(batch)
            if len(batch) < _PAGE_SIZE:
                break
        else:
            raise ValueError("Artičok API exceeded the page limit")
        return self.parse(posts)

    def parse(self, posts: list[dict]) -> list[Event]:
        events: list[Event] = []
        seen: set[str] = set()
        for post in posts:
            if 1 not in post.get("categories", []):
                continue
            event = self._post(post)
            if event and event.native_id not in seen:
                events.append(event)
                seen.add(event.native_id)
        return events

    def _post(self, post: dict) -> Event | None:
        title = clean(soup(unescape(post.get("title", {}).get("rendered", ""))).get_text(" "))
        published = post.get("date", "")
        try:
            pub_date = datetime.fromisoformat(published)
        except (TypeError, ValueError):
            return None
        dates = list(_DATE.finditer(title))
        if not dates:
            return None

        def event_date(match: re.Match[str], previous_year: int | None = None,
                       previous_month: int | None = None) -> tuple[int, int, int]:
            day = int(match.group("day"))
            month_text = match.group("month").lower()
            month = int(month_text) if month_text.isdigit() else MONTHS.get(month_text, 0)
            year = int(match.group("year")) if match.group("year") else (previous_year or pub_date.year)
            if (not match.group("year") and month == 1
                    and ((previous_year is None and pub_date.month == 12) or previous_month == 12)):
                year += 1
            return year, month, day

        first = dates[0]
        year, month, day = event_date(first)
        second = dates[1] if len(dates) > 1 and _RANGE.fullmatch(title[first.end():dates[1].start()]) else None
        if second and not first.group("year") and second.group("year"):
            year = int(second.group("year")) - (month == 12 and event_date(second)[1] == 1)
        tail_start = second.end() if second else first.end()
        tail = title[tail_start:]
        time = _TIME.match(tail)
        hour = int(time.group("hour")) if time else 0
        minute = int(time.group("minute") or 0) if time else 0
        # Bare digits after the date are a time only when followed by a range or "hodin".
        if time and not (time.group("minute") is not None or time.group("suffix") or _RANGE.match(tail[time.end():])):
            time = None
            hour = minute = 0
        try:
            start = datetime(year, month, day, hour, minute, tzinfo=TZ)
        except ValueError:
            return None
        end = None
        end_date = event_date(second, year, month) if second else (year, month, day)
        consumed = time.end() if time else 0
        if time:
            remainder = tail[time.end():]
            end_time = _TIME.match(remainder) if _RANGE.match(remainder) else None
            if end_time:
                end_hour = int(end_time.group("hour"))
                end_minute = int(end_time.group("minute") or 0)
                try:
                    end = datetime(*end_date, end_hour, end_minute, tzinfo=TZ)
                except ValueError:
                    return None
                if end <= start:
                    return None
                consumed += end_time.end()
            elif second:
                try:
                    end = datetime(*end_date, 23, 59, tzinfo=TZ)
                except ValueError:
                    return None
                if end < start:
                    return None
        elif second:
            end_year, end_month, end_day = end_date
            try:
                end = datetime(end_year, end_month, end_day, 23, 59, tzinfo=TZ)
            except ValueError:
                return None
            if end < start:
                return None

        display_title = clean(re.sub(r"^[\s,.:\-–—]+|[\s,.:\-–—]+$", "",
                                     title[:first.start()] + " " + tail[consumed:])) or title
        content = soup(post.get("content", {}).get("rendered", ""))
        content_text = clean(content.get_text(" "))
        description = content_text[:500]
        embedded = post.get("_embedded") or {}
        media = embedded.get("wp:featuredmedia") or []
        image = media[0].get("source_url") if media and isinstance(media[0], dict) else None
        terms = embedded.get("wp:term") or []
        category = next((clean(term.get("name")) for group in terms if isinstance(group, list)
                         for term in group if isinstance(term, dict) and term.get("taxonomy") == "category"
                         and term.get("id") != 1), None)
        link = post.get("link") or self.cfg.page_url
        return self.event(
            title=display_title, start=start, end=end, all_day=time is None,
            url=urljoin(self.cfg.page_url, link), place_raw=self.cfg.place,
            venue="Vinotéka IN VINO" if _VENUE.search(content_text) else self.cfg.extra.get("venue", "Galerie Artičok"),
            native_category=category, description=description, image=image,
            native_id=f"{post.get('id')}|{start.isoformat()}",
        )
