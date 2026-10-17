"""Free-form address -> VOE ids, never silently swapping street types (spec §6)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .address_parse import normalize_house, parse_query, parse_voe_street, search_stem, street_matches
from .models import StreetName
from .voe_client import AcItem


@dataclass(frozen=True)
class StreetChoice:
    item: AcItem
    parsed: StreetName


@dataclass(frozen=True)
class Resolution:
    kind: Literal["found", "choose_street", "choose_house", "not_found"]
    street: StreetChoice | None = None
    house: AcItem | None = None
    street_choices: tuple[StreetChoice, ...] = ()
    house_choices: tuple[AcItem, ...] = ()


def memory_key(city_id: str, text: str) -> str:
    return f"{city_id}|{re.sub(r'\s+', ' ', text).strip().lower()}"


class Resolver:
    def __init__(self, client, memory):
        self.client = client
        self.memory = memory

    def resolve(self, text: str, city: AcItem) -> Resolution:
        key = memory_key(city.id, text)
        hit = self.memory.get(key)
        if hit:
            street = AcItem(hit["street"]["value"], hit["street"]["id"])
            return Resolution("found", StreetChoice(street, parse_voe_street(street.value)),
                              AcItem(hit["house"]["value"], hit["house"]["id"]))

        query = parse_query(text)
        if not query.street.name:
            return Resolution("not_found")
        candidates = [StreetChoice(it, parse_voe_street(it.value))
                      for it in self.client.streets(city.id, search_stem(query.street))]
        matches = tuple(c for c in candidates if street_matches(query.street, c.parsed))
        if not matches:
            return Resolution("not_found")
        if len(matches) > 1:
            return Resolution("choose_street", street_choices=matches)
        return self.resolve_house(city, matches[0], query.house or "", remember_as=text)

    def resolve_house(self, city: AcItem, street: StreetChoice, house_text: str,
                      remember_as: str | None = None) -> Resolution:
        house = normalize_house(house_text) if house_text.strip() else ""
        digits = re.match(r"\d+", house)
        if not digits:
            return Resolution("choose_house", street=street)
        options = tuple(self.client.houses(street.item.id, digits.group(0)))
        exact = next((h for h in options if normalize_house(h.value) == house), None)
        if exact is None:
            return Resolution("choose_house", street=street, house_choices=options)
        # remember only if the text itself names this house, so the key never maps to another one
        typed = parse_query(remember_as).house if remember_as else None
        if typed and normalize_house(typed) == house:
            self.memory.put(memory_key(city.id, remember_as), {
                "street": {"value": street.item.value, "id": street.item.id},
                "house": {"value": exact.value, "id": exact.id},
            })
        return Resolution("found", street, exact)
