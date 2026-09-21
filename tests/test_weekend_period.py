from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

from mostek_kultura import render
from mostek_kultura.config import load_config
from mostek_kultura.model import Event

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "mostek_kultura/templates/index.html.j2"


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 9, 21), (date(2026, 9, 25), date(2026, 9, 27))),  # Mon
        (date(2026, 9, 24), (date(2026, 9, 25), date(2026, 9, 27))),  # Thu
        (date(2026, 9, 25), (date(2026, 9, 25), date(2026, 9, 27))),  # Fri
        (date(2026, 9, 26), (date(2026, 9, 25), date(2026, 9, 27))),  # Sat
        (date(2026, 9, 27), (date(2026, 9, 25), date(2026, 9, 27))),  # Sun
        (date(2026, 12, 31), (date(2027, 1, 1), date(2027, 1, 3))),  # year boundary
        (date(2026, 4, 30), (date(2026, 5, 1), date(2026, 5, 3))),  # month boundary
    ],
)
def test_summary_weekend_is_friday_through_sunday(monkeypatch, today, expected):
    monday = today - timedelta(days=today.weekday())
    days = [monday + timedelta(days=n) for n in (3, 4, 5, 6, 7)]
    events = [
        Event(title=d.strftime("%A"), start=datetime.combine(d, time(18)), source="test")
        for d in days
    ]
    monkeypatch.setattr(render, "today", lambda: today)
    monkeypatch.setattr(render, "now", lambda: datetime.combine(today, time(12)))

    summary = render.build_summary(events, load_config(ROOT / "config.yaml"), [])

    start, end = expected
    selected = summary["weekend"]
    assert [item["date"] for item in selected["events"]] == [
        (start + timedelta(days=n)).isoformat() for n in range(3)
    ]
    assert selected["count"] == sum(start <= d <= end for d in days)


@pytest.mark.parametrize(
    ("today", "expected_start"),
    [
        ("2026-09-21", "2026-09-25"),  # Mon
        ("2026-09-24", "2026-09-25"),  # Thu
        ("2026-09-25", "2026-09-25"),  # Fri
        ("2026-09-26", "2026-09-25"),  # Sat
        ("2026-09-27", "2026-09-25"),  # Sun
        ("2026-12-31", "2027-01-01"),
        ("2026-04-30", "2026-05-01"),
    ],
)
def test_frontend_weekend_tab_uses_friday_to_sunday(today, expected_start):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to evaluate the frontend date constants")

    source = TEMPLATE.read_text(encoding="utf-8")
    declarations = "\n".join(
        re.search(pattern, source).group(0)
        for pattern in (
            r"(?m)^const today=fmtDate\(new Date\(\)\);$",
            r"(?m)^const dateRange=.*$",
            r"(?m)^const addDays=.*$",
            r"(?m)^const dow=.*$",
            r"(?m)^const weekendStart=.*$",
            r"(?m)^const TABS=.*$",
        )
    )
    declarations = declarations.replace(
        "const today=fmtDate(new Date());", "const today=globalThis.__TODAY__;"
    )
    declarations = declarations.replace(
        "const dateRange=MostkulturaDateRange;", "const dateRange=globalThis.__DATE_RANGE__;"
    )
    script = (
        "const vm=require('node:vm');"
        f"const range=require({json.dumps(str(ROOT / 'mostek_kultura/static/date-range.js'))});"
        f"const code={json.dumps(declarations + ';globalThis.__RESULT__=TABS;')};"
        f"const context={{__TODAY__:{json.dumps(today)},__DATE_RANGE__:range}};"
        "vm.runInNewContext(code,context);"
        "process.stdout.write(JSON.stringify(context.__RESULT__));"
    )
    tabs = json.loads(subprocess.check_output([node, "-e", script], text=True))
    weekend = next(tab for tab in tabs if tab[0] == "weekend")
    assert weekend == ["weekend", "Pá–Ne", [expected_start, (date.fromisoformat(expected_start) + timedelta(days=2)).isoformat()]]
