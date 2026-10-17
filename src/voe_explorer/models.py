"""Core data types shared across the app."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StreetName:
    kind: str | None      # canonical street type, e.g. "вулиця", "провулок"
    ordinal: int | None   # 1 for "1-й"
    name: str             # lowercase, unified apostrophes, collapsed spaces


@dataclass(frozen=True)
class AddressQuery:
    street: StreetName
    house: str | None
