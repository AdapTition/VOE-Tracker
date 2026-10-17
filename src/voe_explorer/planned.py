"""Planned works list (/disconnection/planned, spec §5.4) and matching it to a saved address."""
from __future__ import annotations

import calendar
import html as htmllib
import re
from datetime import datetime, timedelta

from .address_parse import normalize_house, parse_plain_street, parse_voe_street, street_matches
from .models import PlannedWork, SavedAddress, StreetName


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _dt(text: str) -> datetime | None:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _streets(addresses: str) -> tuple[tuple[StreetName, tuple[str, ...]], ...]:
    if ":" in addresses:
        addresses = addresses.split(":", 1)[1]
    out = []
    for segment in addresses.split(";"):
        segment = segment.strip()
        if " " not in segment:
            continue
        street_text, houses = segment.rsplit(" ", 1)
        street = parse_plain_street(street_text)
        if street.name:
            out.append((street, tuple(h.strip() for h in houses.split(",") if h.strip())))
    return tuple(out)


def parse_planned_html(html: str) -> list[PlannedWork]:
    works = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        cells = {cls.split()[0]: _text(body)
                 for cls, body in re.findall(r'<td class="([^"]+)"[^>]*>(.*?)</td>', row, flags=re.S)}
        start, end = _dt(cells.get("accbegin", "")), _dt(cells.get("accend_plan", ""))
        if not start or not end or "addresses" not in cells:
            continue
        works.append(PlannedWork(
            id=cells.get("accidentid", ""), kind=cells.get("acctype", ""), status=cells.get("status", ""),
            start=start, end=end, settlement=cells.get("city_list", ""), streets=_streets(cells["addresses"])))
    return works


def parse_region_options(html: str) -> dict[str, str]:
    m = re.search(r'<select[^>]*name="region".*?</select>', html, flags=re.S)
    if not m:
        return {}
    return {v: _text(t) for v, t in re.findall(r'<option value="([^"]+)"[^>]*>(.*?)</option>', m.group(0), flags=re.S)}


def city_name(city_value: str) -> str:
    m = re.match(r"^\S+?\.\.?\s*(.*?)\s*(\(|$)", city_value.strip())
    return m.group(1) if m else city_value


def region_for_city(city_value: str, regions: dict[str, str]) -> str | None:
    m = re.search(r"\(([^/)]*)", city_value)
    district = m.group(1).strip() if m else ""
    if district.endswith("Район"):
        stem = district[: -len("Район")].strip()[:5]
    elif district.endswith("Область"):
        name = city_name(city_value)
        if name == "Вінниця":
            return "23" if "23" in regions else None
        stem = name[:5]
    else:
        return None
    return next((code for code, title in regions.items() if title.endswith("р-н") and title.startswith(stem)), None)


def _same_street(a: StreetName, b: StreetName) -> bool:
    if a.kind and b.kind and a.kind != b.kind:
        return False
    if a.ordinal != b.ordinal:
        return False
    na, nb = StreetName(None, None, a.name), StreetName(None, None, b.name)
    return street_matches(na, nb) and street_matches(nb, na)


def _house_in(house: str, entries: tuple[str, ...]) -> bool:
    for e in entries:
        r = re.fullmatch(r"(\d+)-(\d+)", e)
        if r and house.isdigit() and int(r.group(1)) <= int(house) <= int(r.group(2)):
            return True
        if normalize_house(e) == house:
            return True
    return False


def works_for_address(addr: SavedAddress, works: list[PlannedWork], now: datetime,
                      horizon: timedelta = timedelta(days=7)) -> list[PlannedWork]:
    street = parse_voe_street(addr.street_value)
    house = normalize_house(addr.house_value)
    town = city_name(addr.city_value).upper()
    out = []
    for w in works:
        if w.end <= now or w.start > now + horizon or w.settlement.upper() != town:
            continue
        if any(_same_street(street, s) and _house_in(house, hs) for s, hs in w.streets):
            out.append(w)
    return sorted(out, key=lambda w: w.start)


def months_to_fetch(now: datetime) -> list[tuple[int, int]]:
    months = [(now.year, now.month)]
    last_day = calendar.monthrange(now.year, now.month)[1]
    if last_day - now.day <= 7:
        months.append((now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1))
    return months
