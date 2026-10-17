"""Is voe.com.ua alive? Classification of attempts and the history timeline (spec §8)."""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable

from . import config
from .net import FetchResult, Net

PROBE_PATH = "/disconnection/detailed/autocomplete/read_city?q=%D0%92%D1%96%D0%BD"


class Health(str, Enum):
    OK = "ok"
    SLOW = "slow"
    DOWN = "down"
    OFFLINE = "offline"


def classify(result: FetchResult, expect_json_list: bool) -> Health:
    if result.status != 200 or result.body is None:
        return Health.DOWN
    if expect_json_list:
        try:
            data = json.loads(result.body)
        except ValueError:
            return Health.DOWN
        if not isinstance(data, list) or not data:
            return Health.DOWN
    return Health.SLOW if result.elapsed_s > config.SLOW_S else Health.OK


def internet_ok() -> bool:
    try:
        with urllib.request.urlopen("https://www.google.com/generate_204", timeout=5) as r:
            return r.status == 204
    except Exception:
        return False


def probe(net: Net, internet_check: Callable[[], bool] = internet_ok) -> tuple[Health, FetchResult]:
    result = net.get(PROBE_PATH)
    state = classify(result, expect_json_list=True)
    if state == Health.DOWN and not internet_check():
        state = Health.OFFLINE
    return state, result


@dataclass(frozen=True)
class Segment:
    start: datetime
    end: datetime
    state: str   # "ok" | "slow" | "down" | "offline" | "nodata"


@dataclass(frozen=True)
class HealthStats:
    down_count: int
    down_total: timedelta
    avg_s: float | None
    max_s: float | None


def segments(probes: list[tuple[datetime, str, float]], start: datetime, end: datetime,
             max_gap: timedelta = timedelta(seconds=300)) -> list[Segment]:
    raw: list[Segment] = []
    pts = sorted(p for p in probes if start <= p[0] <= end)
    if not pts:
        return [Segment(start, end, "nodata")]
    if pts[0][0] > start:
        raw.append(Segment(start, pts[0][0], "nodata"))
    for i, (at, state, _) in enumerate(pts):
        nxt = pts[i + 1][0] if i + 1 < len(pts) else end
        if nxt - at <= max_gap:
            raw.append(Segment(at, nxt, state))
        else:
            # the last reading is trusted only briefly; a long silence means the app was not running
            if i + 1 == len(pts):
                raw.append(Segment(at, min(nxt, at + max_gap), state))
                if at + max_gap < nxt:
                    raw.append(Segment(at + max_gap, nxt, "nodata"))
            else:
                raw.append(Segment(at, nxt, "nodata"))
    merged: list[Segment] = []
    for s in raw:
        if s.end <= s.start:
            continue
        if merged and merged[-1].state == s.state and merged[-1].end == s.start:
            merged[-1] = Segment(merged[-1].start, s.end, s.state)
        else:
            merged.append(s)
    return merged


def stats(probes: list[tuple[datetime, str, float]], segs: list[Segment]) -> HealthStats:
    downs = [s for s in segs if s.state == "down"]
    times = [e for _, state, e in probes if state in ("ok", "slow")]
    return HealthStats(
        down_count=len(downs),
        down_total=sum((s.end - s.start for s in downs), timedelta()),
        avg_s=round(sum(times) / len(times), 3) if times else None,
        max_s=max(times) if times else None,
    )


def indicator_text(state: Health, elapsed_s: float | None) -> str:
    if state == Health.OK:
        return f"VOE відповідає · {elapsed_s:.1f} с"
    if state == Health.SLOW:
        return f"VOE повільний · {elapsed_s:.1f} с"
    if state == Health.OFFLINE:
        return "Немає інтернету"
    return "VOE не відповідає"
