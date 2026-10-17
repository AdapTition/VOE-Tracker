"""Core data types shared across the app."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class HourState(str, Enum):
    ON = "on"
    OFF = "off"
    POSSIBLE = "possible"
    OFF_FIRST_HALF = "off_first_half"
    OFF_SECOND_HALF = "off_second_half"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DaySchedule:
    label: str            # "сб 17.10"
    day: date | None
    is_today: bool
    hours: tuple[HourState, ...]   # exactly 24


@dataclass(frozen=True)
class Outage:
    reason: str | None
    start: datetime | None
    end: datetime | None


@dataclass(frozen=True)
class ParsedSchedule:
    power_off_now: bool
    outage: Outage | None
    message_lines: tuple[str, ...]
    warning: str | None
    days: tuple[DaySchedule, ...]
    unknown_classes: frozenset[str]


class ParseError(Exception):
    """VOE answered, but not in a shape we understand."""


@dataclass(frozen=True)
class StreetName:
    kind: str | None      # canonical street type, e.g. "вулиця", "провулок"
    ordinal: int | None   # 1 for "1-й"
    name: str             # lowercase, unified apostrophes, collapsed spaces


@dataclass(frozen=True)
class AddressQuery:
    street: StreetName
    house: str | None
