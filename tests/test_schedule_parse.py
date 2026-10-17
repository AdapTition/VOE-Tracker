from datetime import date, datetime
from pathlib import Path

import pytest

from voe_explorer.models import HourState, Outage, ParseError
from voe_explorer.schedule_parse import extract_insert_html, parse_schedule_html

FIX = Path(__file__).parent / "fixtures"


def test_emergency_fixture():
    raw = (FIX / "2026-10-17_emergency_1-botanichnyi-2.json").read_text("utf-8")
    p = parse_schedule_html(extract_insert_html(raw), datetime(2026, 10, 17, 11, 0))
    assert p.power_off_now is True
    assert p.outage == Outage("Аварійне відключення", datetime(2026, 10, 17, 9, 16), datetime(2026, 10, 18, 7, 16))
    assert p.warning.startswith("Увага!")
    assert len(p.days) == 1 and p.days[0].label == "сб 17.10" and p.days[0].day == date(2026, 10, 17) and p.days[0].is_today
    assert p.days[0].hours == (HourState.ON,) * 24
    assert p.unknown_classes == frozenset()


def test_no_outage_fixture():
    p = parse_schedule_html((FIX / "2026-10-17_no-outage_soborna-1.html").read_text("utf-8"), datetime(2026, 10, 17, 10, 0))
    assert p.power_off_now is False and p.outage is None
    assert "не зафіксовано" in p.message_lines[0]


def test_synthetic_multi_day_year_boundary_and_states():
    p = parse_schedule_html((FIX / "synthetic_gpv_two_days.html").read_text("utf-8"), datetime(2026, 12, 31, 22, 0))
    assert [d.day for d in p.days] == [date(2026, 12, 31), date(2027, 1, 1)]
    assert {HourState.OFF, HourState.POSSIBLE, HourState.OFF_FIRST_HALF, HourState.OFF_SECOND_HALF, HourState.UNKNOWN} <= set(p.days[0].hours)
    assert p.days[0].hours[6] == HourState.OFF and p.days[0].hours[9] == HourState.OFF_FIRST_HALF
    assert p.days[1].hours[:4] == (HourState.OFF,) * 4 and not p.days[1].is_today
    assert p.unknown_classes == frozenset({"weird_new_state"})


def test_missing_current_day_class_uses_date_match():
    html = (FIX / "2026-10-17_no-outage_soborna-1.html").read_text("utf-8").replace(" current_day", "")
    assert parse_schedule_html(html, datetime(2026, 10, 17, 10, 0)).days[0].is_today


@pytest.mark.parametrize("body", ["error code: 502", "<html><body>Cloudflare</body></html>", "[]"])
def test_garbage_raises(body):
    with pytest.raises(ParseError):
        parse_schedule_html(extract_insert_html(body) if body.startswith("[") else body, datetime(2026, 10, 17))
