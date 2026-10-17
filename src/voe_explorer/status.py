"""Turning parsed VOE data into the one status line a card shows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from .models import HourState, ParsedSchedule, PlannedWork


class Level(str, Enum):
    ON = "on"
    OFF = "off"
    POSSIBLE = "possible"
    STALE = "stale"
    SITE_CHANGED = "site_changed"


@dataclass(frozen=True)
class CardStatus:
    level: Level
    headline: str
    reason: str | None
    until: datetime | None
    source: str | None
    data_at: datetime | None


STALE_AFTER = timedelta(minutes=15)
ALL_CLEAR = "не зафіксовано"
HEADLINES = {
    Level.ON: "Світло є",
    Level.OFF: "Немає світла",
    Level.POSSIBLE: "Можливе відключення",
    Level.STALE: "Не вдалося оновити",
    Level.SITE_CHANGED: "Сайт VOE змінився — потрібна нова версія програми",
}
_RANK = {Level.ON: 0, Level.POSSIBLE: 1, Level.OFF: 2}
_HOUR = timedelta(hours=1)
_HALF = timedelta(minutes=30)


def _slots(parsed: ParsedSchedule) -> list[tuple[datetime, HourState]]:
    out = []
    for d in parsed.days:
        if d.day is None:
            continue
        base = datetime(d.day.year, d.day.month, d.day.day)
        out.extend((base + h * _HOUR, s) for h, s in enumerate(d.hours))
    return sorted(out)


def _schedule_candidate(parsed: ParsedSchedule, now: datetime):
    slots = _slots(parsed)
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    idx = next((i for i, (t, _) in enumerate(slots) if t == hour_start), None)
    if idx is None:
        return None
    state = slots[idx][1]
    first_half = now.minute < 30
    if state in (HourState.POSSIBLE, HourState.UNKNOWN):
        return (Level.POSSIBLE, None, None, "за графіком")
    off_now = (state == HourState.OFF
               or (state == HourState.OFF_FIRST_HALF and first_half)
               or (state == HourState.OFF_SECOND_HALF and not first_half))
    if not off_now:
        return (Level.ON, None, None, None)
    if state == HourState.OFF_FIRST_HALF:
        return (Level.OFF, None, hour_start + _HALF, "за графіком")
    end = hour_start + _HOUR
    for t, s in slots[idx + 1:]:
        if t != end:
            break
        if s == HourState.OFF:
            end = t + _HOUR
        elif s == HourState.OFF_FIRST_HALF:
            end = t + _HALF
            break
        else:
            break
    return (Level.OFF, None, end, "за графіком")


def _make(level: Level, reason, until, source, data_at) -> CardStatus:
    return CardStatus(level, HEADLINES[level], reason, until, source, data_at)


def derive_status(parsed: ParsedSchedule | None, fetched_at: datetime | None, parse_failed: bool,
                  planned_now: PlannedWork | None, now: datetime) -> CardStatus:
    if parse_failed:
        return _make(Level.SITE_CHANGED, None, None, None, fetched_at)
    if parsed is None or fetched_at is None or abs(now - fetched_at) > STALE_AFTER:  # abs: clock moved back (DST)
        return _make(Level.STALE, None, None, None, fetched_at)

    candidates = []
    if parsed.power_off_now:
        reason = parsed.outage.reason if parsed.outage else None
        until = parsed.outage.end if parsed.outage else None
        candidates.append((Level.OFF, reason, until, reason.lower() if reason else "повідомлення VOE"))
    if planned_now is not None:
        candidates.append((Level.OFF, planned_now.kind, planned_now.end, "планові роботи"))
    sched = _schedule_candidate(parsed, now)
    if sched is not None:
        candidates.append(sched)
    if not candidates:
        # «Світло є» needs a positive signal: the all-clear text or an ON slot for this hour
        all_clear = any(ALL_CLEAR in line.lower() for line in parsed.message_lines)
        candidates.append((Level.ON, None, None, None) if all_clear else (Level.POSSIBLE, None, None, None))

    best = max(candidates, key=lambda c: _RANK[c[0]])  # max keeps the first of equals
    if best[0] == Level.ON:
        return _make(Level.ON, None, None, None, fetched_at)
    return _make(best[0], best[1], best[2], best[3], fetched_at)
