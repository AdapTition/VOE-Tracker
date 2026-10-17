from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from voe_explorer.models import SavedAddress
from voe_explorer.net import FetchResult
from voe_explorer.service import Service
from voe_explorer.storage import AddressStore, Db
from voe_explorer.voe_client import ScheduleFetch

FIX = Path(__file__).parent / "fixtures"
EMERGENCY = (FIX / "2026-10-17_emergency_1-botanichnyi-2.json").read_text("utf-8")
PLANNED = (FIX / "2026-10-17_planned-page_vinnytsia-2026-10.html").read_text("utf-8")
VIN = "м.. Вінниця (Вінницька Область/М.Вінниця)"


def ok(body, at=datetime(2026, 10, 17, 11, 0)):
    return FetchResult("https://www.voe.com.ua/x", at, 200, 0.4, body, None)


def failed(at):
    return FetchResult("https://www.voe.com.ua/x", at, 502, 0.1, "error code: 502", "HTTP 502")


def synthetic_json():
    import json
    html = (FIX / "synthetic_gpv_two_days.html").read_text("utf-8")
    return json.dumps([{"command": "insert", "data": html}])


class FakeClient:
    def __init__(self):
        self.net = SimpleNamespace(on_attempt=None)
        self.schedules = []

    def schedule(self, addr):
        return self.schedules.pop(0)

    def planned_form_page(self):
        return ok(PLANNED)

    def planned_page(self, region, year, month):
        assert region == "23"
        return ok(PLANNED)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path):
    client = FakeClient()
    store = AddressStore(tmp_path / "addresses.json")
    db = Db(tmp_path / "voe.sqlite3")
    clock = Clock(datetime(2026, 10, 17, 11, 0))
    svc = Service(client, SimpleNamespace(), store, db, tmp_path / "samples", clock=clock, internet_check=lambda: True)
    return SimpleNamespace(client=client, store=store, db=db, clock=clock, svc=svc, samples=tmp_path / "samples")


def add(env, street="провулок. 1-й Ботанічний", house="2"):
    a = SavedAddress("a1", "Батьки", VIN, "510100000", street, "837", house, "29419")
    env.store.add(a)
    return a


def test_refresh_emergency_snapshot(env):
    add(env)
    env.client.schedules.append(ScheduleFetch(ok(EMERGENCY), EMERGENCY))
    env.svc.refresh_address("a1")
    card = env.svc.snapshot()["cards"][0]
    assert card["level"] == "off" and card["headline"] == "Немає світла"
    assert card["reason"] == "Аварійне відключення" and card["until"] == "07:16 завтра"
    assert card["address"] == "1-й пров. Ботанічний, 2" and card["label"] == "Батьки"
    assert len(card["today"]["hours"]) == 24 and card["data_at"] == "11:00" and card["loading"] is False


def test_failed_refresh_keeps_last_data_then_stale(env):
    add(env)
    env.client.schedules.append(ScheduleFetch(ok(EMERGENCY), EMERGENCY))
    env.svc.refresh_address("a1")
    env.clock.t += timedelta(minutes=20)
    env.client.schedules.append(ScheduleFetch(failed(env.clock.t), None))
    env.svc.refresh_address("a1")
    card = env.svc.snapshot()["cards"][0]
    assert card["level"] == "stale" and card["data_at"] == "11:00" and card["today"] is not None


def test_never_fetched_is_loading_and_stale(env):
    add(env)
    card = env.svc.snapshot()["cards"][0]
    assert card["level"] == "stale" and card["loading"] is True and card["today"] is None


def test_parse_error_marks_site_changed_and_saves_sample(env):
    add(env)
    env.client.schedules.append(ScheduleFetch(ok("[]"), "[]"))
    env.svc.refresh_address("a1")
    assert env.svc.snapshot()["cards"][0]["level"] == "site_changed"
    assert len(list(env.samples.iterdir())) == 1


def test_unknown_classes_save_sample(env):
    add(env)
    raw = synthetic_json()
    env.client.schedules.append(ScheduleFetch(ok(raw), raw))
    env.svc.refresh_address("a1")
    assert len(list(env.samples.iterdir())) == 1
    assert env.svc.snapshot()["cards"][0]["level"] in ("on", "off", "possible")


def test_response_history_stored(env):
    add(env)
    raw = synthetic_json()
    env.client.schedules += [ScheduleFetch(ok(EMERGENCY), EMERGENCY), ScheduleFetch(ok(raw), raw)]
    env.svc.refresh_address("a1")
    env.svc.refresh_address("a1")
    assert len(env.db.responses("a1", "schedule")) == 2


def test_planned_line_on_card(env):
    add(env, street="вулиця. Стрілецька", house="16")
    env.svc.refresh_planned()
    card = env.svc.snapshot()["cards"][0]
    assert {"text": "вт 20.10, 09:00–16:30"} in card["planned"]
    assert card["planned"].count({"text": "вт 20.10, 09:00–16:30"}) == 1   # two VOE records, same slot
    assert env.db.responses(None, "planned")


def test_http_attempts_recorded_but_network_errors_left_to_probe(env):
    hook = env.client.net.on_attempt
    hook(ok("<html></html>"))
    hook(FetchResult("u", datetime(2026, 10, 17, 11, 1), None, 40.0, None, "timeout"))
    rows = env.db.probes_between(datetime(2026, 10, 17), datetime(2026, 10, 18))
    assert [s for _, s, _ in rows] == ["ok"]


def test_failed_planned_fetch_retries_soon(env, monkeypatch):
    add(env)
    env.client.planned_form_page = lambda: failed(env.clock())
    assert env.svc.refresh_planned() is False            # nothing fetched: VOE down or no Wi-Fi yet
    env.client.planned_form_page = lambda: ok(PLANNED)
    assert env.svc.refresh_planned() is True

    # the loop waits the short retry interval after a failed cycle, the long one after success
    waits, results = [], [False, True]
    monkeypatch.setattr(env.svc._stop, "wait", lambda t: (waits.append(t), len(waits) == 2)[1] and env.svc._stop.set())
    env.svc._loop(lambda: results.pop(0), interval=10800, retry=300)
    assert waits == [300, 10800]
