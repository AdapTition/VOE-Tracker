import urllib.parse

import pytest

from fakes import FakeOpener, ac_body
from voe_explorer.models import SavedAddress
from voe_explorer.net import Net
from voe_explorer.voe_client import AcItem, VoeClient, VoeUnavailable


def make(answers):
    opener = FakeOpener(answers)
    attempts, sleeps = [], []
    net = Net(opener=opener, on_attempt=attempts.append, sleep=sleeps.append)
    return VoeClient(net), net, opener, attempts, sleeps


def test_cyrillic_query_is_utf8_encoded():
    client, _, opener, _, _ = make([(200, "[]")])
    client.streets("510100000", "Ботан")
    assert opener.requests[0].full_url.endswith(
        "/disconnection/detailed/autocomplete/read_street/510100000?q=%D0%91%D0%BE%D1%82%D0%B0%D0%BD")


def test_retries_on_502_then_ok():
    _, net, _, attempts, sleeps = make([(502, "error code: 502"), (502, "error code: 502"), (200, "[]")])
    result = net.get("/x")
    assert result.status == 200 and result.ok
    assert len(attempts) == 3 and sleeps == [2, 2]


def test_gives_up_after_3():
    client, net, _, _, _ = make([(502, "error code: 502")] * 6)
    assert net.get("/x").status == 502
    with pytest.raises(VoeUnavailable):
        client.streets("1", "Соборн")


def test_timeout_is_retried_and_reported():
    _, net, _, attempts, _ = make([TimeoutError("t"), (200, "ok")])
    assert net.get("/x").ok
    assert attempts[0].status is None and attempts[0].error


def test_ac_items_parsed():
    client, *_ = make([(200, ac_body(("вулиця. Соборна", "1652")))])
    assert client.streets("510100000", "Соборн") == [AcItem("вулиця. Соборна", "1652")]


def test_ac_html_body_is_unavailable():
    client, *_ = make([(200, "<html><body>oops</body></html>")])
    with pytest.raises(VoeUnavailable):
        client.cities("Він")


def test_schedule_posts_expected_form():
    page = '<form id="disconnection-detailed-search-form"><input type="hidden" name="form_build_id" value="form-XYZ" /></form>'
    client, _, opener, _, _ = make([(200, page), (200, '[{"command":"insert","data":"<p>x</p>"}]')])
    addr = SavedAddress("a1", "Батьки", "м.. Вінниця (Вінницька Область/М.Вінниця)", "510100000",
                        "провулок. 1-й Ботанічний", "837", "2", "29419")
    fetch = client.schedule(addr)
    post = opener.requests[1]
    assert post.full_url.endswith("/disconnection/detailed?ajax_form=1&_wrapper_format=drupal_ajax")
    body = post.data.decode("ascii")
    assert "form_build_id=form-XYZ" in body and "street_id=837" in body and "house_id=29419" in body
    assert "_triggering_element_value=%D0%9F%D0%BE%D0%BA%D0%B0%D0%B7%D0%B0%D1%82%D0%B8" in body
    assert dict(urllib.parse.parse_qsl(body))["city"] == addr.city_value
    assert fetch.raw_json == '[{"command":"insert","data":"<p>x</p>"}]'


def test_schedule_page_failure_returns_no_json():
    client, *_ = make([(502, "error code: 502")] * 3)
    addr = SavedAddress("a1", "x", "c", "1", "s", "2", "3", "4")
    fetch = client.schedule(addr)
    assert fetch.raw_json is None and fetch.result.status == 502
