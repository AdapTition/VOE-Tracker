"""Recon probe: full address -> schedule cycle against voe.com.ua using stdlib only."""
import json, re, sys, time, urllib.parse, urllib.request, http.cookiejar

BASE = "https://www.voe.com.ua"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"
OUT = sys.argv[1]

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def req(path, data=None, tries=5):
    for i in range(tries):
        t0 = time.time()
        r = urllib.request.Request(BASE + path, data=data, headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"})
        try:
            with op.open(r, timeout=40) as resp:
                body = resp.read().decode("utf-8")
                print(f"  {resp.status} {time.time()-t0:.1f}s {path[:70]}", file=sys.stderr)
                return body
        except urllib.error.HTTPError as e:
            print(f"  {e.code} {time.time()-t0:.1f}s {path[:70]} (retry)", file=sys.stderr)
            time.sleep(2)
    raise RuntimeError("gave up")


def ac(method, parent, q):
    p = f"/disconnection/detailed/autocomplete/{method}" + (f"/{parent}" if parent is not None else "")
    items = json.loads(req(p + "?q=" + urllib.parse.quote(q)))
    return [(x["value"], re.search(r'data-id="([^"]*)"', x["label"]).group(1)) for x in items]


page = req("/disconnection/detailed")
form = page[page.index('id="disconnection-detailed-search-form"'):]
fbid = re.search(r'name="form_build_id" value="([^"]+)"', form).group(1)

city = ac("read_city", None, "Вінн")[0]
street = ac("read_street", city[1], "Соборн")[0]
house = ac("read_house", street[1], "1")[0]
print(city, street, house, file=sys.stderr)

data = urllib.parse.urlencode({
    "search_type": "0", "city": city[0], "city_id": city[1], "street": street[0], "street_id": street[1],
    "house": house[0], "house_id": house[1], "form_build_id": fbid, "form_id": "disconnection_detailed_search_form",
    "_triggering_element_name": "search", "_triggering_element_value": "Показати", "_drupal_ajax": "1",
}).encode()
resp = json.loads(req("/disconnection/detailed?ajax_form=1&_wrapper_format=drupal_ajax", data))
html = next(c["data"] for c in resp if c.get("command") == "insert")
open(OUT, "w", encoding="utf-8").write(html)
print("saved", len(html), file=sys.stderr)
