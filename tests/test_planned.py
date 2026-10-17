from datetime import datetime
from pathlib import Path

from voe_explorer.models import SavedAddress, StreetName
from voe_explorer.planned import (
    city_name,
    months_to_fetch,
    parse_planned_html,
    parse_region_options,
    region_for_city,
    works_for_address,
)

FIX = Path(__file__).parent / "fixtures"
HTML = (FIX / "2026-10-17_planned-page_vinnytsia-2026-10.html").read_text("utf-8")
VIN = "м.. Вінниця (Вінницька Область/М.Вінниця)"


def address(street, house):
    return SavedAddress("a", "x", VIN, "510100000", street, "1", house, "2")


def test_parse_fixture():
    works = parse_planned_html(HTML)
    assert len(works) == 20
    w = next(w for w in works if w.id == "2826054")
    assert w.start == datetime(2026, 10, 20, 9, 0) and w.end == datetime(2026, 10, 20, 16, 30)
    assert w.settlement == "ВІННИЦЯ" and w.kind == "Планове відключення" and w.status == "Підтверджено"
    assert (StreetName("вулиця", None, "стрілецька"), ("16", "18", "20", "26", "28", "30")) in w.streets
    assert all(s.name for s, _ in w.streets)


def test_matches_strilecka_16():
    works = parse_planned_html(HTML)
    now = datetime(2026, 10, 17, 12, 0)
    ids = {w.id for w in works_for_address(address("вулиця. Стрілецька", "16"), works, now)}
    assert "2826054" in ids
    assert "2826054" not in {w.id for w in works_for_address(address("вулиця. Стрілецька", "16А"), works, now)}
    assert works_for_address(address("провулок. Стрілецький", "16"), works, now) == []


def test_range_houses_match():
    html = HTML.replace("вулиця Стрілецька 16,18,20,26,28,30", "вулиця Стрілецька 11-33")
    works = parse_planned_html(html)
    assert works_for_address(address("вулиця. Стрілецька", "17"), works, datetime(2026, 10, 17))
    assert not works_for_address(address("вулиця. Стрілецька", "35"), works, datetime(2026, 10, 17))


def test_past_and_far_future_excluded():
    works = parse_planned_html(HTML)
    a = address("вулиця. Стрілецька", "16")
    assert "2826054" not in {w.id for w in works_for_address(a, works, datetime(2026, 10, 21))}
    assert works_for_address(a, works, datetime(2026, 10, 1)) == []


def test_region_mapping():
    regions = parse_region_options(HTML)
    assert regions["23"] == "Вінницькі МЕМ" and regions["41"] == "Жмеринський р-н"
    assert region_for_city(VIN, regions) == "23"
    assert region_for_city("смт.. Літин (Літинський Район/Смт Літин)", regions) == "27"
    assert region_for_city("м.. Гнівань (Тиврівський Район/Смт Тиврів)", regions) == "26"
    assert region_for_city("м.. Жмеринка (Вінницька Область/М.Вінниця)", regions) == "41"
    assert region_for_city("смт.. Стрижавка (Вінницький Район/М.Вінниця)", regions) is None


def test_city_name():
    assert city_name(VIN) == "Вінниця"
    assert city_name("с.. Літинка (Літинський Район/Смт Літин)") == "Літинка"


def test_months_to_fetch():
    assert months_to_fetch(datetime(2026, 10, 17)) == [(2026, 10)]
    assert months_to_fetch(datetime(2026, 12, 28)) == [(2026, 12), (2027, 1)]
