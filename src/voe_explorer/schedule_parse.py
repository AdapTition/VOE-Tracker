"""Parsing the Drupal AJAX answer of /disconnection/detailed."""
from __future__ import annotations

import html as htmllib
import json
import re
from datetime import date, datetime

from .models import DaySchedule, HourState, Outage, ParsedSchedule, ParseError

_MODIFIERS = {"cell", "current_day", "grey", "past", "day_col", "legend", "head", ""}
_STATE_BY_CLASS = {
    "no_disconnection": HourState.ON,
    "non_scheduled": HourState.ON,
    "confirmed": HourState.OFF,
    "possible": HourState.POSSIBLE,
    "first_half": HourState.OFF_FIRST_HALF,
    "second_half": HourState.OFF_SECOND_HALF,
}
_TIME = re.compile(r"(\d{2}):(\d{2})\s+(\d{4})\.(\d{2})\.(\d{2})")


def extract_insert_html(raw_json: str) -> str:
    try:
        commands = json.loads(raw_json)
    except ValueError as e:
        raise ParseError(f"not JSON: {e}") from e
    if not isinstance(commands, list):
        raise ParseError("AJAX answer is not a list")
    for c in commands:
        if isinstance(c, dict) and c.get("command") == "insert" and isinstance(c.get("data"), str):
            return c["data"]
    raise ParseError("no insert command in AJAX answer")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _time_after(label: str, lines: list[str]) -> datetime | None:
    for line in lines:
        if label in line:
            m = _TIME.search(line)
            if m:
                hh, mm, y, mo, d = map(int, m.groups())
                return datetime(y, mo, d, hh, mm)
    return None


def _day_from_label(label: str, fetched_at: datetime) -> date | None:
    m = re.search(r"(\d{1,2})\.(\d{1,2})", label)
    if not m:
        return None
    d, mo = int(m.group(1)), int(m.group(2))
    year = fetched_at.year
    if mo < fetched_at.month - 6:
        year += 1
    elif mo > fetched_at.month + 6:
        year -= 1
    try:
        return date(year, mo, d)
    except ValueError:
        return None


def _state(classes: list[str], unknown: set[str]) -> HourState:
    tokens = [c for c in classes if c not in _MODIFIERS]
    states = []
    for tok in tokens:
        key = tok.removeprefix("cell-").replace("-", "_")
        if key in _STATE_BY_CLASS:
            states.append(_STATE_BY_CLASS[key])
        else:
            unknown.add(tok)
    if len(states) == 1:
        return states[0]
    return HourState.UNKNOWN


def parse_schedule_html(html: str, fetched_at: datetime) -> ParsedSchedule:
    msg = re.search(r'class="disconnection-detailed-table-message">(.*?)</div>', html, flags=re.S)
    has_container = 'class="disconnection-detailed-table-container"' in html
    if not msg and not has_container:
        raise ParseError("neither message nor schedule table found")

    lines: list[str] = []
    warning = None
    if msg:
        for attrs, body in re.findall(r"<p([^>]*)>(.*?)</p>", msg.group(1), flags=re.S):
            text = _text(body)
            if not text:
                continue
            if "warning" in attrs:
                warning = text
            else:
                lines.append(text)

    power_off_now = any("відсутня електроенергія" in line.lower() for line in lines)
    reason = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("Причина відключення")), None)
    start = _time_after("Час початку", lines)
    end = _time_after("завершення", lines)
    outage = Outage(reason, start, end) if (power_off_now or reason or start or end) else None

    unknown: set[str] = set()
    days: list[DaySchedule] = []
    current: dict | None = None
    if has_container:
        container = html[html.index('class="disconnection-detailed-table-container"'):]
        for cls, inner in re.findall(r'<div\s+class="disconnection-detailed-table-cell ([^"]*)">([^<]*)', container):
            classes = cls.split()
            if "head" in classes:
                continue
            if "day_col" in classes:
                if current is not None:
                    days.append(_finish_day(current, fetched_at))
                current = {"label": _text(inner), "today": "current_day" in classes, "hours": []}
            elif "cell" in classes and current is not None:
                current["hours"].append(_state(classes, unknown))
        if current is not None:
            days.append(_finish_day(current, fetched_at))

    return ParsedSchedule(
        power_off_now=power_off_now,
        outage=outage,
        message_lines=tuple(lines),
        warning=warning,
        days=tuple(days),
        unknown_classes=frozenset(unknown),
    )


def _finish_day(raw: dict, fetched_at: datetime) -> DaySchedule:
    if len(raw["hours"]) != 24:
        raise ParseError(f"day {raw['label']!r} has {len(raw['hours'])} hour cells")
    day = _day_from_label(raw["label"], fetched_at)
    return DaySchedule(
        label=raw["label"],
        day=day,
        is_today=raw["today"] or day == fetched_at.date(),
        hours=tuple(raw["hours"]),
    )
