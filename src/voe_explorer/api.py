"""Methods the HTML UI calls through pywebview (window.pywebview.api.*).

Attributes are underscore-prefixed so pywebview does not try to expose them to JS.
"""
from __future__ import annotations

import functools
import os
import subprocess
import sys
import threading
import uuid
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

from .address_parse import parse_query, parse_voe_street
from .health import segments, stats
from .install import install_self
from .models import ParseError, SavedAddress
from .planned import city_name, parse_planned_html
from .resolver import Resolution, StreetChoice
from .schedule_parse import extract_insert_html, parse_schedule_html
from .voe_client import AcItem, VoeUnavailable

VOE_DOWN = "Сайт VOE зараз не відповідає. Спробуйте ще раз за хвилину."
GENERIC = "Щось пішло не так. Спробуйте ще раз."


def _safe(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except VoeUnavailable:
            return {"error": VOE_DOWN}
        except Exception:
            return {"error": GENERIC}
    return wrapper


def _item(d: dict) -> AcItem:
    return AcItem(d["value"], d["id"])


def _resolution(res: Resolution) -> dict:
    def street(c: StreetChoice | None):
        return {"value": c.item.value, "id": c.item.id} if c else None

    def house(h: AcItem | None):
        return {"value": h.value, "id": h.id} if h else None

    return {
        "kind": res.kind, "street": street(res.street), "house": house(res.house),
        "street_choices": [street(c) for c in res.street_choices],
        "house_choices": [house(h) for h in res.house_choices],
    }


def _understood_schedule(body: str | None, at: datetime) -> dict:
    try:
        p = parse_schedule_html(extract_insert_html(body or ""), at)
    except ParseError as e:
        return {"error": f"Не вдалося розібрати: {e}"}
    return {
        "power_off_now": p.power_off_now,
        "reason": p.outage.reason if p.outage else None,
        "start": f"{p.outage.start:%d.%m %H:%M}" if p.outage and p.outage.start else None,
        "end": f"{p.outage.end:%d.%m %H:%M}" if p.outage and p.outage.end else None,
        "message_lines": list(p.message_lines),
        "warning": p.warning,
        "days": [{"label": d.label, "hours": [h.value for h in d.hours]} for d in p.days],
        "unknown_classes": sorted(p.unknown_classes),
    }


class Api:
    def __init__(self, service, resolver, client, addresses, db, window_ref, memory=None):
        self._service = service
        self._resolver = resolver
        self._client = client
        self._addresses = addresses
        self._db = db
        self._window = window_ref
        self._memory = memory

    @_safe
    def get_state(self) -> dict:
        return self._service.snapshot()

    @_safe
    def search_cities(self, q: str) -> list[dict]:
        return [{"value": c.value, "id": c.id, "name": city_name(c.value)} for c in self._client.cities(q)]

    @_safe
    def resolve(self, text: str, city: dict) -> dict:
        return _resolution(self._resolver.resolve(text, _item(city)))

    @_safe
    def choose_street(self, city: dict, street: dict, house_text: str, text: str | None = None) -> dict:
        item = _item(street)
        choice = StreetChoice(item, parse_voe_street(item.value))
        if not house_text.strip() and text:
            house_text = parse_query(text).house or ""
        return _resolution(self._resolver.resolve_house(_item(city), choice, house_text, remember_as=text))

    @_safe
    def add_address(self, label: str, city: dict, street: dict, house: dict) -> dict:
        addr = SavedAddress(uuid.uuid4().hex[:12], label.strip() or "Адреса", city["value"], city["id"],
                            street["value"], street["id"], house["value"], house["id"])
        self._addresses.add(addr)

        def refresh():
            try:
                self._service.refresh_address(addr.id)
                self._service.refresh_planned()   # the new address may be in a region not fetched yet
            except Exception:
                pass   # the regular refresh loop will try again

        threading.Thread(target=refresh, daemon=True).start()
        return {"id": addr.id}

    @_safe
    def rename(self, id: str, label: str) -> dict:
        self._addresses.rename(id, label.strip() or "Адреса")
        return {}

    @_safe
    def move(self, id: str, delta: int) -> dict:
        self._addresses.move(id, int(delta))
        return {}

    @_safe
    def remove(self, id: str) -> dict:
        self._addresses.remove(id)
        return {}

    @_safe
    def refresh_now(self) -> dict:
        self._service.request_refresh()
        return {}

    @_safe
    def get_raw(self, id: str | None, kind: str) -> dict:
        items = []
        for r in self._db.responses(id or None, kind):
            item = {"id": r.id, "at": f"{r.at:%d.%m %H:%M:%S}", "status": r.status,
                    "elapsed_s": round(r.elapsed_s, 2), "url": r.url, "html": None, "json": None}
            if kind == "schedule":
                item["json"] = r.body
                try:
                    item["html"] = extract_insert_html(r.body or "")
                except ParseError:
                    item["html"] = None
                item["understood"] = _understood_schedule(r.body, r.at)
            elif kind == "planned":
                item["html"] = r.body
                item["understood"] = {"works": len(parse_planned_html(r.body or ""))}
            else:
                item["json"] = r.body
                item["understood"] = {}
            items.append(item)
        return {"items": items}

    @_safe
    def save_raw(self, response_id: int) -> dict:
        import webview
        r = self._db.response(int(response_id))
        window = self._window()
        if r is None or window is None:
            return {"error": GENERIC}
        ext = "html" if r.kind == "planned" else "json"
        path = window.create_file_dialog(webview.SAVE_DIALOG, save_filename=f"voe-{r.kind}-{r.at:%Y%m%d-%H%M%S}.{ext}")
        if not path:
            return {"path": None}
        path = path[0] if isinstance(path, (list, tuple)) else path
        Path(path).write_text(r.body or "", encoding="utf-8")
        return {"path": str(path)}

    @_safe
    def health_history(self, window: str) -> dict:
        now = datetime.now()
        start = now - (timedelta(days=7) if window == "week" else timedelta(days=1))
        probes = self._db.probes_between(start, now)
        segs = segments(probes, start, now)
        st = stats(probes, segs)
        return {
            "start": start.isoformat(), "end": now.isoformat(),
            "segments": [{"start": s.start.isoformat(), "end": s.end.isoformat(), "state": s.state} for s in segs],
            "stats": {"down_count": st.down_count, "down_minutes": round(st.down_total.total_seconds() / 60),
                      "avg_s": st.avg_s, "max_s": st.max_s},
        }

    @_safe
    def install_self(self) -> dict:
        target = install_self(Path(sys.executable), os.environ)
        subprocess.Popen([str(target)], close_fds=True)
        window = self._window()
        if window is not None:
            window.destroy()
        return {"path": str(target)}

    @_safe
    def dismiss_install(self) -> dict:
        self._service.install_offer = False
        if self._memory is not None:
            self._memory.put("__install_dismissed", {"at": datetime.now().isoformat()})
        return {}

    @_safe
    def open_url(self, url: str) -> dict:
        if isinstance(url, str) and url.startswith("https://github.com/"):
            webbrowser.open(url)
        return {}
