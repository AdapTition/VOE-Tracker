from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from voe_explorer.api import Api
from voe_explorer.net import FetchResult
from voe_explorer.storage import AddressStore, Db
from voe_explorer.voe_client import AcItem, VoeUnavailable

FIX = Path(__file__).parent / "fixtures"
EMERGENCY = (FIX / "2026-10-17_emergency_1-botanichnyi-2.json").read_text("utf-8")


class BrokenResolver:
    def resolve(self, text, city):
        raise VoeUnavailable("502")


def make(tmp_path, resolver=None, client=None):
    db = Db(tmp_path / "voe.sqlite3")
    store = AddressStore(tmp_path / "addresses.json")
    service = SimpleNamespace(snapshot=lambda: {"cards": []}, refresh_address=lambda i: None, refresh_planned=lambda: None,
                              request_refresh=lambda: None, install_offer=False)
    return Api(service, resolver or BrokenResolver(), client, store, db, lambda: None), db, store


def test_methods_never_raise(tmp_path):
    api, _, _ = make(tmp_path)
    out = api.resolve("1-й пров. Ботанічний 2", {"value": "м.. Вінниця", "id": "510100000"})
    assert out == {"error": "Сайт VOE зараз не відповідає. Спробуйте ще раз за хвилину."}


def test_get_raw_includes_understood_and_raw(tmp_path):
    api, db, _ = make(tmp_path)
    db.add_response("a1", "schedule", FetchResult("https://www.voe.com.ua/x", datetime(2026, 10, 17, 11), 200, 0.4, EMERGENCY, None), "h")
    item = api.get_raw("a1", "schedule")["items"][0]
    assert "Причина відключення" in item["html"] and item["json"] == EMERGENCY
    assert item["understood"]["reason"] == "Аварійне відключення"
    assert item["status"] == 200 and item["at"] == "17.10 11:00:00"


def test_get_raw_garbage_is_explained(tmp_path):
    api, db, _ = make(tmp_path)
    db.add_response("a1", "schedule", FetchResult("u", datetime(2026, 10, 17, 11), 200, 0.4, "[]", None), None)
    item = api.get_raw("a1", "schedule")["items"][0]
    assert "error" in item["understood"]


def test_open_url_rejects_non_github(tmp_path, monkeypatch):
    api, _, _ = make(tmp_path)
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    api.open_url("https://evil.example/x")
    api.open_url("https://github.com/me/voe-explorer-releases/releases/tag/v0.2.0")
    assert opened == ["https://github.com/me/voe-explorer-releases/releases/tag/v0.2.0"]


def test_add_address_stores_and_returns_id(tmp_path):
    api, _, store = make(tmp_path)
    out = api.add_address("Батьки", {"value": "м.. Вінниця", "id": "510100000"},
                          {"value": "провулок. 1-й Ботанічний", "id": "837"}, {"value": "2", "id": "29419"})
    assert store.get(out["id"]).street_id == "837" and store.get(out["id"]).label == "Батьки"


def test_search_cities_adds_short_name(tmp_path):
    client = SimpleNamespace(cities=lambda q: [AcItem("м.. Вінниця (Вінницька Область/М.Вінниця)", "510100000")])
    api, _, _ = make(tmp_path, client=client)
    assert api.search_cities("Він") == [{"value": "м.. Вінниця (Вінницька Область/М.Вінниця)", "id": "510100000", "name": "Вінниця"}]


def test_choose_street_takes_house_from_original_text(tmp_path):
    seen = {}

    class R:
        def resolve_house(self, city, street, house_text, remember_as=None):
            seen.update(house=house_text, remember=remember_as, street=street.item.id)
            from voe_explorer.resolver import Resolution
            return Resolution("choose_house", street=street)

    api, _, _ = make(tmp_path, resolver=R())
    out = api.choose_street({"value": "м.. Вінниця", "id": "510100000"},
                            {"value": "проїзд. Ботанічний", "id": "1137"}, "", "Ботанічний 5")
    assert out["kind"] == "choose_house"
    assert seen == {"house": "5", "remember": "Ботанічний 5", "street": "1137"}


def test_add_address_refreshes_schedule_and_planned(tmp_path):
    import threading
    done = threading.Event()
    calls = []
    api, _, _ = make(tmp_path)
    api._service.refresh_address = lambda i: calls.append(("schedule", i))
    api._service.refresh_planned = lambda: (calls.append(("planned",)), done.set())
    out = api.add_address("Друзі", {"value": "м.. Вінниця", "id": "510100000"},
                          {"value": "вулиця. Стрілецька", "id": "1748"}, {"value": "16", "id": "38512"})
    assert done.wait(2)
    assert ("schedule", out["id"]) in calls and ("planned",) in calls
