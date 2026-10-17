"""The VOE endpoints the official site itself uses (spec §5)."""
from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass

from .models import SavedAddress
from .net import FetchResult, Net

_AC = "/disconnection/detailed/autocomplete/"
_DETAILED = "/disconnection/detailed"
_PLANNED = "/disconnection/planned"


class VoeUnavailable(Exception):
    """Autocomplete did not return a JSON list with HTTP 200."""


@dataclass(frozen=True)
class AcItem:
    value: str
    id: str


@dataclass(frozen=True)
class ScheduleFetch:
    result: FetchResult
    raw_json: str | None


def _form_fields(page: str, form_id: str) -> dict[str, str] | None:
    i = page.find(f'id="{form_id}"')
    if i < 0:
        return None
    form = page[i:]
    end = form.find("</form>")
    form = form[:end] if end >= 0 else form
    m = re.search(r'name="form_build_id" value="([^"]+)"', form)
    if not m:
        return None
    fields = {"form_build_id": m.group(1)}
    op = re.search(r'name="op" value="([^"]*)"', form)
    if op:
        fields["op"] = op.group(1)
    return fields


class VoeClient:
    def __init__(self, net: Net):
        self.net = net

    def _ac(self, path: str, q: str) -> list[AcItem]:
        res = self.net.get(f"{_AC}{path}?q={urllib.parse.quote(q)}")
        if not res.ok:
            raise VoeUnavailable(res.error or f"HTTP {res.status}")
        try:
            items = json.loads(res.body)
        except ValueError as e:
            raise VoeUnavailable("autocomplete answer is not JSON") from e
        if not isinstance(items, list):
            raise VoeUnavailable("autocomplete answer is not a list")
        out = []
        for x in items:
            m = re.search(r'data-id="([^"]*)"', x.get("label", ""))
            if m and x.get("value"):
                out.append(AcItem(x["value"], m.group(1)))
        return out

    def cities(self, q: str) -> list[AcItem]:
        return self._ac("read_city", q)

    def streets(self, city_id: str, q: str) -> list[AcItem]:
        return self._ac(f"read_street/{city_id}", q)

    def houses(self, street_id: str, q: str) -> list[AcItem]:
        return self._ac(f"read_house/{street_id}", q)

    def schedule(self, addr: SavedAddress) -> ScheduleFetch:
        page = self.net.get(_DETAILED)
        fields = _form_fields(page.body or "", "disconnection-detailed-search-form") if page.ok else None
        if fields is None:
            return ScheduleFetch(page, None)
        res = self.net.post(f"{_DETAILED}?ajax_form=1&_wrapper_format=drupal_ajax", {
            "search_type": "0",
            "city": addr.city_value, "city_id": addr.city_id,
            "street": addr.street_value, "street_id": addr.street_id,
            "house": addr.house_value, "house_id": addr.house_id,
            "form_build_id": fields["form_build_id"],
            "form_id": "disconnection_detailed_search_form",
            "_triggering_element_name": "search",
            "_triggering_element_value": "Показати",
            "_drupal_ajax": "1",
        })
        return ScheduleFetch(res, res.body if res.ok else None)

    def planned_form_page(self) -> FetchResult:
        return self.net.get(_PLANNED)

    def planned_page(self, region: str, year: int, month: int) -> FetchResult:
        page = self.net.get(_PLANNED)
        fields = _form_fields(page.body or "", "disconnection-search-form") if page.ok else None
        if fields is None:
            return page
        return self.net.post(_PLANNED, {
            "year": str(year), "month": f"{month:02d}", "region": region,
            "form_build_id": fields["form_build_id"], "form_id": "disconnection_search_form",
            "op": fields.get("op", "Пошук"),
        })
