from datetime import datetime, timedelta

from voe_explorer.models import SavedAddress
from voe_explorer.net import FetchResult
from voe_explorer.storage import AddressStore, Db, MemoryStore, save_sample


def addr(i):
    return SavedAddress(i, f"Назва {i}", "м.. Вінниця", "510100000", "вулиця. Соборна", "1652", "1", "26590")


def test_address_crud_and_order(tmp_path):
    p = tmp_path / "addresses.json"
    s = AddressStore(p)
    for i in "ABC":
        s.add(addr(i))
    s.move("C", -1)
    assert [a.id for a in s.all()] == ["A", "C", "B"]
    s.move("A", -1)
    assert [a.id for a in s.all()] == ["A", "C", "B"]
    s.rename("B", "Батьки")
    s.remove("A")
    again = AddressStore(p)
    assert [(a.id, a.label) for a in again.all()] == [("C", "Назва C"), ("B", "Батьки")]


def test_memory_roundtrip_unicode(tmp_path):
    p = tmp_path / "memory.json"
    MemoryStore(p).put("510100000|1-й пров. ботанічний, 2", {"street": {"value": "провулок. 1-й Ботанічний"}})
    assert MemoryStore(p).get("510100000|1-й пров. ботанічний, 2") == {"street": {"value": "провулок. 1-й Ботанічний"}}
    p.read_bytes().decode("utf-8")
    assert MemoryStore(p).get("missing") is None


def res(at, body="x"):
    return FetchResult("https://www.voe.com.ua/x", at, 200, 0.3, body, None)


def test_response_retention(tmp_path):
    db = Db(tmp_path / "voe.sqlite3")
    t = datetime(2026, 10, 17, 10, 0)
    hashes = [f"h{i}" for i in range(12) for _ in range(2)] + ["h11"] * 3
    for n, h in enumerate(hashes):
        db.add_response("a1", "schedule", res(t + timedelta(minutes=n), body=f"b{n}"), h)
    db.add_response("a2", "schedule", res(t), "zz")
    kept = db.responses("a1", "schedule")
    assert len(kept) == 11
    assert kept[0].body == f"b{len(hashes) - 1}"
    assert {r.content_hash for r in kept} == {f"h{i}" for i in range(2, 12)}
    assert len(db.responses("a2", "schedule")) == 1
    assert db.response(kept[0].id).body == kept[0].body


def test_responses_without_address(tmp_path):
    db = Db(tmp_path / "voe.sqlite3")
    rid = db.add_response(None, "probe", res(datetime(2026, 10, 17)), None)
    assert db.responses(None, "probe")[0].id == rid


def test_probes_between_filters_by_time(tmp_path):
    db = Db(tmp_path / "voe.sqlite3")
    t = datetime(2026, 10, 17, 10, 0)
    for m, state in [(0, "ok"), (2, "down"), (4, "ok"), (60, "slow")]:
        db.add_probe(t + timedelta(minutes=m), "probe", 200, 1.5, state)
    got = db.probes_between(t + timedelta(minutes=1), t + timedelta(minutes=30))
    assert got == [(t + timedelta(minutes=2), "down", 1.5), (t + timedelta(minutes=4), "ok", 1.5)]


def test_save_sample_writes_utf8(tmp_path):
    p = save_sample(tmp_path / "samples", "a1", '{"x": "Причина"}', "unknown classes")
    assert p.exists() and p.name.endswith("_a1.json")
    assert "Причина" in p.read_text("utf-8")
