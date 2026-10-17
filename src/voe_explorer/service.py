"""Background refresh loops and the state snapshot the UI renders."""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from . import config
from .health import Health, classify, indicator_text, internet_ok, probe
from .models import ParsedSchedule, ParseError, PlannedWork, SavedAddress
from .net import FetchResult
from .planned import months_to_fetch, parse_planned_html, parse_region_options, region_for_city, works_for_address
from .schedule_parse import extract_insert_html, parse_schedule_html
from .status import derive_status
from .storage import AddressStore, Db, save_sample

WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "нд")
KIND_ABBR = {"вулиця": "вул.", "провулок": "пров.", "проспект": "просп.", "бульвар": "бул.", "площа": "пл."}


@dataclass
class CardState:
    parsed: ParsedSchedule | None = None
    fetched_at: datetime | None = None
    parse_failed: bool = False
    loading: bool = True


def schedule_hash(p: ParsedSchedule) -> str:
    data = {
        "off": p.power_off_now,
        "outage": [p.outage.reason, str(p.outage.start), str(p.outage.end)] if p.outage else None,
        "days": [[d.label, [h.value for h in d.hours]] for d in p.days],
    }
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode("utf-8")).hexdigest()


def display_address(addr: SavedAddress) -> str:
    kind, _, rest = addr.street_value.partition(". ")
    if not rest:
        kind, rest = "", addr.street_value
    ordinal = ""
    parts = rest.split(" ", 1)
    if len(parts) == 2 and parts[0][:1].isdigit():
        ordinal, rest = parts[0] + " ", parts[1]
    abbr = KIND_ABBR.get(kind, kind)
    return f"{ordinal}{abbr} {rest}".strip() + f", {addr.house_value}"


def _fmt_until(t: datetime | None, now: datetime) -> str | None:
    if t is None:
        return None
    if t.date() == now.date():
        return f"{t:%H:%M}"
    if t.date() == (now + timedelta(days=1)).date():
        return f"{t:%H:%M} завтра"
    return f"{t:%d.%m %H:%M}"


def _fmt_work(w: PlannedWork) -> str:
    start = f"{WEEKDAYS[w.start.weekday()]} {w.start:%d.%m}"
    if w.start.date() == w.end.date():
        return f"{start}, {w.start:%H:%M}–{w.end:%H:%M}"
    return f"{start}, {w.start:%H:%M} – {WEEKDAYS[w.end.weekday()]} {w.end:%d.%m}, {w.end:%H:%M}"


class Service:
    def __init__(self, client, net, addresses: AddressStore, db: Db, samples_dir: Path,
                 clock: Callable[[], datetime] = datetime.now, internet_check: Callable[[], bool] = internet_ok):
        self.client = client
        self.net = net                # separate Net used only for health probes
        self.addresses = addresses
        self.db = db
        self.samples_dir = samples_dir
        self.clock = clock
        self.internet_check = internet_check
        self._lock = threading.Lock()
        self._cards: dict[str, CardState] = {}
        self._works: list[PlannedWork] = []
        self._regions: dict[str, str] = {}
        self._health: tuple[Health, float, datetime] | None = None
        self.update: dict | None = None
        self.install_offer = False
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._threads: list[threading.Thread] = []
        client.net.on_attempt = self._on_attempt

    # --- recording -------------------------------------------------------
    def _on_attempt(self, result: FetchResult) -> None:
        if result.status is None:
            return  # no HTTP answer: could be our own network; the probe decides
        state = classify(result, expect_json_list=False)
        self.db.add_probe(result.at, "request", result.status, result.elapsed_s, state.value)

    def _card(self, addr_id: str) -> CardState:
        return self._cards.setdefault(addr_id, CardState())

    # --- work units --------------------------------------------------------
    def refresh_address(self, addr_id: str) -> None:
        addr = self.addresses.get(addr_id)
        if addr is None:
            return
        with self._lock:
            self._card(addr_id).loading = True
        fetch = self.client.schedule(addr)
        now = self.clock()
        if fetch.raw_json is None:
            self.db.add_response(addr.id, "schedule", fetch.result, None)
            with self._lock:
                card = self._card(addr_id)
                card.loading = False
                if fetch.result.ok:   # page loaded but the form was not there
                    card.parse_failed, card.fetched_at = True, now
            return
        try:
            parsed = parse_schedule_html(extract_insert_html(fetch.raw_json), now)
        except ParseError as e:
            save_sample(self.samples_dir, addr.id, fetch.raw_json, f"ParseError: {e}")
            self.db.add_response(addr.id, "schedule", fetch.result, None)
            with self._lock:
                card = self._card(addr_id)
                card.parse_failed, card.fetched_at, card.loading = True, now, False
            return
        if parsed.unknown_classes:
            save_sample(self.samples_dir, addr.id, fetch.raw_json, f"unknown classes: {sorted(parsed.unknown_classes)}")
        self.db.add_response(addr.id, "schedule", fetch.result, schedule_hash(parsed))
        with self._lock:
            card = self._card(addr_id)
            card.parsed, card.fetched_at, card.parse_failed, card.loading = parsed, now, False, False

    def refresh_all(self) -> None:
        for addr in self.addresses.all():
            if self._stop.is_set():
                return
            self.refresh_address(addr.id)

    def refresh_planned(self) -> bool:
        if not self._regions:
            page = self.client.planned_form_page()
            if page.ok:
                self._regions = parse_region_options(page.body)
        regions = {region_for_city(a.city_value, self._regions) for a in self.addresses.all()} - {None}
        works, any_ok = [], False
        for region in sorted(regions):
            for year, month in months_to_fetch(self.clock()):
                res = self.client.planned_page(region, year, month)
                parsed = parse_planned_html(res.body) if res.ok else []
                digest = hashlib.sha256(repr(parsed).encode("utf-8")).hexdigest() if res.ok else None
                self.db.add_response(None, "planned", res, digest)
                if res.ok:
                    any_ok = True
                    works.extend(parsed)
        if any_ok or not regions:
            with self._lock:
                self._works = works
        # False: nothing could be fetched (VOE down, no Wi-Fi yet) -> the loop retries soon
        return any_ok or (not regions and (bool(self._regions) or not self.addresses.all()))

    def run_probe(self) -> None:
        state, res = probe(self.net, self.internet_check)
        self.db.add_probe(res.at, "probe", res.status, res.elapsed_s, state.value)
        self.db.add_response(None, "probe", res, None)
        with self._lock:
            self._health = (state, res.elapsed_s, res.at)

    def request_refresh(self) -> None:
        self._wake.set()

    # --- snapshot ------------------------------------------------------------
    def snapshot(self) -> dict:
        now = self.clock()
        with self._lock:
            cards = []
            for addr in self.addresses.all():
                card = self._card(addr.id)
                works = works_for_address(addr, self._works, now)
                planned_now = next((w for w in works if w.start <= now < w.end), None)
                st = derive_status(card.parsed, card.fetched_at, card.parse_failed, planned_now, now)
                days = card.parsed.days if card.parsed else ()
                today = next((d for d in days if d.is_today), None)
                others = [d for d in days if d is not today and (today is None or (d.day and today.day and d.day > today.day))]
                cards.append({
                    "id": addr.id, "label": addr.label, "address": display_address(addr),
                    "level": st.level.value, "headline": st.headline, "reason": st.reason,
                    "until": _fmt_until(st.until, now), "source": st.source,
                    "data_at": f"{st.data_at:%H:%M}" if st.data_at else None,
                    "today": {"label": today.label, "hours": [h.value for h in today.hours]} if today else None,
                    "other_days": [{"label": d.label, "hours": [h.value for h in d.hours]} for d in others],
                    "planned": [{"text": t} for t in dict.fromkeys(_fmt_work(w) for w in works)],
                    "loading": card.loading,
                })
            if self._health:
                state, elapsed, at = self._health
                health = {"state": state.value, "text": indicator_text(state, elapsed), "at": f"{at:%H:%M}"}
            else:
                health = {"state": "unknown", "text": "Перевіряємо VOE…", "at": None}
            return {"health": health, "cards": cards, "update": self.update, "install_offer": self.install_offer}

    # --- loops ---------------------------------------------------------------
    def _loop(self, fn: Callable[[], object], interval: float, wake: threading.Event | None = None,
              retry: float | None = None) -> None:
        while not self._stop.is_set():
            try:
                failed = fn() is False
            except Exception:  # a bad cycle must never kill the loop
                failed = True
            wait = retry if (failed and retry is not None) else interval
            if wake is not None:
                wake.wait(wait)
                wake.clear()
            else:
                self._stop.wait(wait)

    def start(self) -> None:
        for fn, interval, wake, retry in ((self.refresh_all, config.REFRESH_S, self._wake, None),
                                          (self.run_probe, config.PROBE_S, None, None),
                                          (self.refresh_planned, config.PLANNED_S, None, config.REFRESH_S)):
            t = threading.Thread(target=self._loop, args=(fn, interval, wake, retry), daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
