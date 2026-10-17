from datetime import datetime, timedelta

from fakes import FakeOpener, ac_body
from voe_explorer.health import Health, Segment, classify, indicator_text, probe, segments, stats
from voe_explorer.net import FetchResult, Net

T = datetime(2026, 10, 17, 10, 0)
LIST = ac_body(("м.. Вінниця", "510100000"))


def r(status, body, elapsed=0.3):
    return FetchResult("u", T, status, elapsed, body, None if status == 200 else "e")


def test_classify():
    assert classify(r(200, LIST), True) == Health.OK
    assert classify(r(200, LIST, 12), True) == Health.SLOW
    assert classify(r(502, "error code: 502"), True) == Health.DOWN
    assert classify(r(None, None), True) == Health.DOWN
    assert classify(r(200, "[]"), True) == Health.DOWN
    assert classify(r(200, "<html>oops</html>"), True) == Health.DOWN
    assert classify(r(200, "<html>page</html>"), False) == Health.OK


def test_probe_ok_and_offline():
    net = Net(opener=FakeOpener([(200, LIST)]), sleep=lambda s: None)
    assert probe(net, lambda: True)[0] == Health.OK
    net = Net(opener=FakeOpener([TimeoutError()] * 3), sleep=lambda s: None)
    state, res = probe(net, lambda: False)
    assert state == Health.OFFLINE and res.status is None
    net = Net(opener=FakeOpener([(502, "x")] * 3), sleep=lambda s: None)
    assert probe(net, lambda: True)[0] == Health.DOWN


def m(minutes):
    return T + timedelta(minutes=minutes)


def test_gap_becomes_nodata():
    probes = [(m(0), "ok", 0.3), (m(2), "ok", 0.3), (m(4), "ok", 0.3), (m(180), "ok", 0.3)]
    assert segments(probes, m(0), m(182)) == [
        Segment(m(0), m(4), "ok"), Segment(m(4), m(180), "nodata"), Segment(m(180), m(182), "ok")]


def test_down_run_merged_and_counted():
    probes = [(m(0), "ok", 0.3), (m(2), "down", 40.0), (m(4), "down", 40.0), (m(6), "down", 40.0), (m(8), "ok", 0.5)]
    segs = segments(probes, m(0), m(10))
    assert segs == [Segment(m(0), m(2), "ok"), Segment(m(2), m(8), "down"), Segment(m(8), m(10), "ok")]
    st = stats(probes, segs)
    assert st.down_count == 1 and st.down_total == timedelta(minutes=6)
    assert st.max_s == 0.5 and st.avg_s == 0.4


def test_offline_not_counted_as_down():
    probes = [(m(0), "ok", 0.3), (m(2), "offline", 5.0), (m(4), "ok", 0.3)]
    segs = segments(probes, m(0), m(6))
    assert stats(probes, segs).down_count == 0


def test_empty_window_is_nodata():
    assert segments([], m(0), m(60)) == [Segment(m(0), m(60), "nodata")]


def test_indicator_text():
    assert indicator_text(Health.OK, 5.8) == "VOE відповідає · 5.8 с"
    assert indicator_text(Health.SLOW, 12.04) == "VOE повільний · 12.0 с"
    assert indicator_text(Health.DOWN, None) == "VOE не відповідає"
    assert indicator_text(Health.OFFLINE, None) == "Немає інтернету"
