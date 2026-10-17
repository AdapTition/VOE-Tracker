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
from .status import STALE_AFTER, derive_status
from .storage import AddressStore, Db, save_sample

WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "нд")
SITE_CHANGED_AFTER = 2          # consecutive unparseable answers before we call the site changed
HEALTH_STALE = timedelta(seconds=2 * config.PROBE_S + config.RETRIES * config.TIMEOUT_S)
JSON_URL_MARKERS = ("_wrapper_format=drupal_ajax", "/autocomplete/")
KIND_ABBR = {"вулиця": "вул.", "провулок": "пров.", "проспект": "просп.", "бульвар": "бул.", "площа": "пл."}


@dataclass
class CardState:
    parsed: ParsedSchedule | None = None
    fetched_at: datetime | None = None    # time of the last answer we could read
    parse_failures: int = 0               # consecutive unreadable answers
    failed_at: datetime | None = None
    loading: bool = True
    started: int = 0                      # sequence of the newest request started
    applied: int = 0                      # sequence of the request whose answer is shown

    @property
    def parse_failed(self) -> bool:
        return self.parse_failures >= SITE_CHANGED_AFTER


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


def _fmt_data_at(t: datetime | None, now: datetime) -> str | None:
    if t is None:
        return None
    if t.date() == now.date():
        return f"{t:%H:%M}"
    if t.date() == (now - timedelta(days=1)).date():
        return f"{t:%H:%M} вчора"
    return f"{t:%H:%M}, {t:%d.%m}"


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
        self._probe_wake = threading.Event()
        self._last_cycle: datetime | None = None
        self._seq = 0
        self._threads: list[threading.Thread] = []
        client.net.on_attempt = self._on_attempt

    # --- recording -------------------------------------------------------
    def _on_attempt(self, result: FetchResult) -> None:
        if result.status is None:
            return  # no HTTP answer: could be our own network; the probe decides
        state = classify(result, expect_json_list=False)
        if state != Health.DOWN and any(m in result.url for m in JSON_URL_MARKERS):
            try:   # a JSON endpoint answering 200 with an HTML error page (Cloudflare) is VOE being down
                json.loads(result.body)
            except ValueError:
                state = Health.DOWN
        self.db.add_probe(result.at, "request", result.status, result.elapsed_s, state.value)

    def _card(self, addr_id: str) -> CardState:
        return self._cards.setdefault(addr_id, CardState())

    # --- work units --------------------------------------------------------
    def refresh_address(self, addr_id: str) -> None:
        addr = self.addresses.get(addr_id)
        if addr is None:
            return
        with self._lock:
            card = self._card(addr_id)
            card.loading = True
            self._seq += 1
            seq = card.started = self._seq
        fetch = self.client.schedule(addr)
        now = self.clock()
        parsed, failure = None, None
        if fetch.raw_json is None:
            if fetch.result.ok:   # page loaded but the form was not there
                failure = "page without the search form"
                save_sample(self.samples_dir, addr.id, fetch.result.body or "", f"ParseError: {failure}")
            self.db.add_response(addr.id, "schedule", fetch.result, None)
        else:
            try:
                parsed = parse_schedule_html(extract_insert_html(fetch.raw_json), now)
            except ParseError as e:
                failure = str(e)
                save_sample(self.samples_dir, addr.id, fetch.raw_json, f"ParseError: {e}")
                self.db.add_response(addr.id, "schedule", fetch.result, None)
            else:
                if parsed.unknown_classes:
                    save_sample(self.samples_dir, addr.id, fetch.raw_json,
                                f"unknown classes: {sorted(parsed.unknown_classes)}")
                self.db.add_response(addr.id, "schedule", fetch.result, schedule_hash(parsed))
        with self._lock:
            card = self._card(addr_id)
            if seq == card.started:
                card.loading = False
            if seq < card.applied:
                return            # a newer answer is already shown
            card.applied = seq
            if parsed is not None:
                card.parsed, card.fetched_at, card.parse_failures, card.failed_at = parsed, now, 0, None
            elif failure is not None:
                card.parse_failures += 1
                card.failed_at = now

    def refresh_all(self) -> None:
        self._last_cycle = self.clock()
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

    def check_voe(self) -> Health:
        """Probe VOE right now (used when an answer looks empty)."""
        self.run_probe()
        with self._lock:
            return self._health[0]

    def request_refresh(self) -> None:
        self._wake.set()

    # --- snapshot ------------------------------------------------------------
    def snapshot(self) -> dict:
        now = self.clock()
        any_stale = False
        with self._lock:
            cards = []
            for addr in self.addresses.all():
                card = self._card(addr.id)
                works = works_for_address(addr, self._works, now)
                planned_now = next((w for w in works if w.start <= now < w.end), None)
                site_changed = (card.parse_failed and card.failed_at is not None
                                and abs(now - card.failed_at) <= STALE_AFTER)
                if site_changed:
                    st = derive_status(None, card.failed_at, True, planned_now, now)
                else:
                    st = derive_status(card.parsed, card.fetched_at, False, planned_now, now)
                    if st.level.value == "stale":
                        any_stale = True
                days = card.parsed.days if card.parsed else ()
                # "today" is the calendar day now, not the day the answer was fetched
                today = next((d for d in days if d.day == now.date()), None) or next(
                    (d for d in days if d.day is None and d.is_today and card.fetched_at
                     and card.fetched_at.date() == now.date()), None)
                others = [d for d in days if d is not today and d.day and d.day > now.date()]
                cards.append({
                    "id": addr.id, "label": addr.label, "address": display_address(addr),
                    "level": st.level.value, "headline": st.headline, "reason": st.reason,
                    "until": _fmt_until(st.until, now), "source": st.source,
                    "data_at": _fmt_data_at(st.data_at, now),
                    "today": {"label": today.label, "hours": [h.value for h in today.hours]} if today else None,
                    "other_days": [{"label": d.label, "hours": [h.value for h in d.hours]} for d in others],
                    "planned": [{"text": t} for t in dict.fromkeys(_fmt_work(w) for w in works)],
                    "loading": card.loading,
                })
            if self._health and abs(now - self._health[2]) <= HEALTH_STALE:
                state, elapsed, at = self._health
                health = {"state": state.value, "text": indicator_text(state, elapsed), "at": f"{at:%H:%M}"}
            else:   # never probed, or the last probe is from before a sleep: don't show it as current
                health = {"state": "unknown", "text": "Перевіряємо VOE…", "at": None}
                if self._health:
                    self._probe_wake.set()
            last = self._last_cycle
        # after sleep the loops may still be waiting out their interval: wake the card refresh now
        if any_stale and (last is None or abs(now - last) > timedelta(seconds=config.REFRESH_S + 60)):
            self.request_refresh()
        return {"health": health, "cards": cards, "update": self.update, "install_offer": self.install_offer}

    # --- loops ---------------------------------------------------------------
    def _loop(self, fn: Callable[[], object], interval: float, wake: threading.Event | None = None,
              retry: float | None = None) -> None:
        while not self._stop.is_set():
            if wake is not None:
                wake.clear()      # a wake-up asked for during this cycle triggers one more cycle
            try:
                failed = fn() is False
            except Exception:  # a bad cycle must never kill the loop
                failed = True
            wait = retry if (failed and retry is not None) else interval
            if wake is not None:
                wake.wait(wait)
            else:
                self._stop.wait(wait)

    def start(self) -> None:
        for fn, interval, wake, retry in ((self.refresh_all, config.REFRESH_S, self._wake, None),
                                          (self.run_probe, config.PROBE_S, self._probe_wake, None),
                                          (self.refresh_planned, config.PLANNED_S, None, config.REFRESH_S)):
            t = threading.Thread(target=self._loop, args=(fn, interval, wake, retry), daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._probe_wake.set()
