import pytest

from voe_explorer.address_parse import (
    normalize_house,
    parse_plain_street,
    parse_query,
    parse_voe_street,
    search_stem,
    street_matches,
)
from voe_explorer.models import AddressQuery, StreetName

BOTAN1 = StreetName("провулок", 1, "ботанічний")


@pytest.mark.parametrize("text", [
    "1-й пров. Ботанічний, 10", "1 провулок Ботанічний 10",
    "перший Ботанічний провулок, 10", "Ботанічний 1-й пров 10", "1й пров Ботанічний,10",
])
def test_parse_query_variants_equal(text):
    assert parse_query(text) == AddressQuery(BOTAN1, "10")


def test_parse_query_without_kind_or_house():
    assert parse_query("Ботанічний") == AddressQuery(StreetName(None, None, "ботанічний"), None)


def test_parse_query_kind_only_street():
    assert parse_query("вул. Соборна 1") == AddressQuery(StreetName("вулиця", None, "соборна"), "1")


def test_apostrophes_unified():
    assert parse_query("вул. Гоголя-П’ятницька 3").street.name == parse_query("вул. Гоголя-П'ятницька 3").street.name


@pytest.mark.parametrize("value,expected", [
    ("провулок. 1-й Ботанічний", StreetName("провулок", 1, "ботанічний")),
    ("проїзд. Ботанічний", StreetName("проїзд", None, "ботанічний")),
    ("вулиця. Ботанічна", StreetName("вулиця", None, "ботанічна")),
    ("вулиця. Юрія Смирнова/1 провулок Український", StreetName("вулиця", None, "юрія смирнова/1 провулок український")),
])
def test_parse_voe_street(value, expected):
    assert parse_voe_street(value) == expected


def test_parse_plain_street():
    assert parse_plain_street("вулиця Стрілецька") == StreetName("вулиця", None, "стрілецька")
    assert parse_plain_street("* 1-й Маріі Литвиненко-Вольгемут") == StreetName(None, 1, "маріі литвиненко-вольгемут")


@pytest.mark.parametrize("raw", ["12А", "12a", "12A", "12-А", "12 а", " 12а "])
def test_normalize_house_letter(raw):
    assert normalize_house(raw) == "12А"


def test_normalize_house_fraction():
    assert normalize_house("10 / 2") == "10/2"


def test_search_stem_is_name_prefix_without_kind_or_ordinal():
    assert search_stem(BOTAN1) == "Ботан"
    assert search_stem(StreetName(None, None, "юрія смирнова")) == "Смирн"


def test_street_matches_kind_and_ordinal_exact():
    assert street_matches(BOTAN1, StreetName("провулок", 1, "ботанічний"))
    assert not street_matches(BOTAN1, StreetName("провулок", 2, "ботанічний"))
    assert not street_matches(BOTAN1, StreetName("вулиця", None, "ботанічна"))
    assert not street_matches(BOTAN1, StreetName("провулок", None, "ботанічний"))


def test_unspecified_kind_or_ordinal_matches_any():
    q = StreetName(None, None, "ботанічний")
    assert street_matches(q, StreetName("провулок", 2, "ботанічний"))
    assert street_matches(q, StreetName("проїзд", None, "ботанічний"))


def test_street_matches_tolerates_adjective_ending_and_partial_name():
    q = StreetName("вулиця", None, "ботанічний")
    assert street_matches(q, StreetName("вулиця", None, "ботанічна"))
    assert street_matches(StreetName(None, None, "коцюбинського"), StreetName("проспект", None, "михайла коцюбинського"))


def test_street_name_starting_with_number():
    q = parse_query("8 Березня 10")
    assert q.house == "10"
    assert street_matches(q.street, parse_voe_street("вулиця. 8 Березня"))
    assert street_matches(parse_query("вул. 8 Березня, 10").street, parse_voe_street("вулиця. 8 Березня"))
    assert not street_matches(q.street, parse_voe_street("вулиця. 9 Травня"))
    assert parse_plain_street("вулиця 8 Березня") == parse_voe_street("вулиця. 8 Березня")


# live VOE autocomplete for "Хмель" (2026-10-17)
HMEL = ["вулиця. Богдана Хмельницького", "вулиця. Хмельницьке шосе", "провулок. 1-й Хмельницьке шосе",
        "провулок. 2-й Хмельницьке шосе", "провулок. Хмельницьке шосе"]


def _hits(text):
    q = parse_query(text).street
    return [v for v in HMEL if street_matches(q, parse_voe_street(v))]


def test_shose_named_as_vulytsia_by_voe():
    assert _hits("Хмельницьке шосе 81") == ["вулиця. Хмельницьке шосе"]
    assert _hits("вул. Хмельницьке шосе, 81") == ["вулиця. Хмельницьке шосе"]
    assert _hits("шосе Хмельницьке 81") == ["вулиця. Хмельницьке шосе"]
    assert _hits("1-й пров. Хмельницьке шосе 5") == ["провулок. 1-й Хмельницьке шосе"]
    assert parse_plain_street("вулиця Хмельницьке шосе") == parse_voe_street("вулиця. Хмельницьке шосе")
