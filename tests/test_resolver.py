from voe_explorer.resolver import Resolver
from voe_explorer.voe_client import AcItem

CITY = AcItem("м.. Вінниця (Вінницька Область/М.Вінниця)", "510100000")
STREETS = [
    AcItem("вулиця. Ботанічна", "1136"), AcItem("проїзд. Ботанічний", "1137"),
    AcItem("провулок. 1-й Ботанічний", "837"), AcItem("провулок. 2-й Ботанічний", "944"),
    AcItem("провулок. 3-й Ботанічний", "1032"), AcItem("провулок. Ботанічний", "33570"),
]
HOUSES = {
    "837": [AcItem("2", "29419"), AcItem("20", "29420"), AcItem("22", "29421")],
    "1136": [AcItem("12А", "500"), AcItem("10/2", "501")],
    "1137": [AcItem("5", "600")],
}


class FakeClient:
    def __init__(self):
        self.calls = []

    def streets(self, city_id, q):
        self.calls.append(("streets", city_id, q))
        return [s for s in STREETS if q.lower() in s.value.lower()]

    def houses(self, street_id, q):
        self.calls.append(("houses", street_id, q))
        return [h for h in HOUSES.get(street_id, []) if h.value.startswith(q)]


class DictMemory(dict):
    def put(self, key, value):
        self[key] = value


def resolver():
    client = FakeClient()
    return Resolver(client, DictMemory()), client


def test_exact_ordinal_and_kind_found():
    r, _ = resolver()
    res = r.resolve("1-й пров. Ботанічний, 2", CITY)
    assert res.kind == "found" and res.street.item.id == "837" and res.house == AcItem("2", "29419")


def test_no_kind_many_kinds_asks():
    r, _ = resolver()
    for text in ("Ботанічний 10", "Ботанічна 10"):
        res = r.resolve(text, CITY)
        assert res.kind == "choose_street" and len(res.street_choices) == 6 and res.house is None


def test_no_ordinal_with_ordinal_candidates_asks():
    r, _ = resolver()
    res = r.resolve("пров. Ботанічний 2", CITY)
    assert res.kind == "choose_street"
    assert sorted(c.item.id for c in res.street_choices) == sorted(["837", "944", "1032", "33570"])


def test_single_candidate_auto():
    r, _ = resolver()
    res = r.resolve("проїзд Ботанічний 5", CITY)
    assert res.kind == "found" and res.street.item.id == "1137" and res.house.id == "600"


def test_house_variant_match():
    r, _ = resolver()
    res = r.resolve("вул. Ботанічна 12a", CITY)
    assert res.kind == "found" and res.house.value == "12А"
    assert r.resolve("вул. Ботанічна 10 / 2", CITY).kind == "found"


def test_unknown_house_offers_list():
    r, _ = resolver()
    res = r.resolve("1-й пров. Ботанічний 3", CITY)
    assert res.kind == "choose_house" and res.street.item.id == "837"


def test_memory_short_circuits():
    r, client = resolver()
    assert r.resolve("1-й пров. Ботанічний, 2", CITY).kind == "found"
    n = len(client.calls)
    again = r.resolve("1-й  пров. Ботанічний, 2", CITY)
    assert again.kind == "found" and again.house.id == "29419" and len(client.calls) == n


def test_chosen_street_is_remembered():
    r, client = resolver()
    first = r.resolve("Ботанічний 5", CITY)
    choice = next(c for c in first.street_choices if c.item.id == "1137")
    assert r.resolve_house(CITY, choice, "5", remember_as="Ботанічний 5").kind == "found"
    n = len(client.calls)
    assert r.resolve("Ботанічний 5", CITY).street.item.id == "1137" and len(client.calls) == n


def test_not_found():
    r, _ = resolver()
    assert r.resolve("вул. Неіснуюча 1", CITY).kind == "not_found"


def test_other_house_is_not_remembered_under_original_text():
    r, client = resolver()
    res = r.resolve("1-й пров. Ботанічний 3", CITY)
    assert res.kind == "choose_house"
    assert r.resolve_house(CITY, res.street, "20", remember_as="1-й пров. Ботанічний 3").kind == "found"
    client.calls.clear()
    again = r.resolve("1-й пров. Ботанічний 3", CITY)
    assert again.kind == "choose_house" and client.calls  # asked VOE again, no silent house 20
