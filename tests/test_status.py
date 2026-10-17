from datetime import date, datetime, timedelta

from voe_explorer.models import DaySchedule, HourState, Outage, ParsedSchedule, PlannedWork, StreetName
from voe_explorer.status import Level, derive_status

H = HourState
TODAY = date(2026, 10, 17)


def sched(hours=None, off_now=False, outage=None, lines=("x",)):
    hours = hours or [H.ON] * 24
    return ParsedSchedule(off_now, outage, tuple(lines), None,
                          (DaySchedule("сб 17.10", TODAY, True, tuple(hours)),), frozenset())


def at(h, m=0):
    return datetime(2026, 10, 17, h, m)


def test_message_off_beats_green_table():
    out = Outage("Аварійне відключення", at(9, 16), datetime(2026, 10, 18, 7, 16))
    s = derive_status(sched(off_now=True, outage=out), at(11), False, None, at(11))
    assert s.level == Level.OFF and s.headline == "Немає світла"
    assert s.reason == "Аварійне відключення" and s.until == out.end and s.source == "аварійне відключення"


def test_table_off_current_hour():
    hours = [H.ON] * 24
    hours[14] = hours[15] = hours[16] = H.OFF
    s = derive_status(sched(hours), at(14, 10), False, None, at(14, 10))
    assert s.level == Level.OFF and s.source == "за графіком" and s.until == at(17)


def test_half_hours():
    first = [H.ON] * 24
    first[14] = H.OFF_FIRST_HALF
    s = derive_status(sched(first), at(14, 10), False, None, at(14, 10))
    assert s.level == Level.OFF and s.until == at(14, 30)
    assert derive_status(sched(first), at(14, 40), False, None, at(14, 40)).level == Level.ON
    second = [H.ON] * 24
    second[14] = H.OFF_SECOND_HALF
    assert derive_status(sched(second), at(14, 40), False, None, at(14, 40)).level == Level.OFF


def test_possible_and_unknown_are_yellow():
    for state in (H.POSSIBLE, H.UNKNOWN):
        hours = [H.ON] * 24
        hours[14] = state
        s = derive_status(sched(hours), at(14, 10), False, None, at(14, 10))
        assert s.level == Level.POSSIBLE and s.headline == "Можливе відключення"


def test_worst_wins():
    hours = [H.ON] * 24
    hours[11] = H.POSSIBLE
    out = Outage("Аварійне відключення", at(9), at(20))
    assert derive_status(sched(hours, True, out), at(11), False, None, at(11)).level == Level.OFF
    work = PlannedWork("1", "Планове відключення", "Підтверджено", at(9), at(16, 30), "ВІННИЦЯ",
                       ((StreetName("вулиця", None, "стрілецька"), ("16",)),))
    s = derive_status(sched(), at(11), False, work, at(11))
    assert s.level == Level.OFF and s.source == "планові роботи" and s.until == at(16, 30)


def test_stale_never_green():
    fetched = at(11) - timedelta(hours=3)
    s = derive_status(sched(), fetched, False, None, at(11))
    assert s.level == Level.STALE and s.headline == "Не вдалося оновити" and s.data_at == fetched
    s2 = derive_status(None, None, False, None, at(11))
    assert s2.level == Level.STALE and s2.data_at is None


def test_site_changed():
    s = derive_status(None, at(11), True, None, at(11))
    assert s.level == Level.SITE_CHANGED
    assert s.headline == "Сайт VOE змінився — потрібна нова версія програми"


def test_all_clear():
    s = derive_status(sched(lines=("За Вашою адресою наразі не зафіксовано аварійних та планових відключень.",)),
                      at(11), False, None, at(11))
    assert s.level == Level.ON and s.headline == "Світло є" and s.data_at == at(11)
