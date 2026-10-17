"""Capture the raw VOE schedule response for 1-й пров. Ботанічний, 2 (Вінниця)."""
import json, re, sys, time, urllib.parse, urllib.request, urllib.error, http.cookiejar

BASE = "https://www.voe.com.ua"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"
OUT = sys.argv[1]
log = open(OUT + ".log", "w", encoding="utf-8")
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def req(path, data=None, tries=6):
    for i in range(tries):
        t0 = time.time()
        r = urllib.request.Request(BASE + path, data=data, headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"})
        try:
            with op.open(r, timeout=40) as resp:
                body = resp.read().decode("utf-8")
                print(f"{resp.status} {time.time()-t0:.1f}s {path[:80]}", file=log, flush=True)
                return body
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            print(f"ERR {e} {time.time()-t0:.1f}s {path[:80]}", file=log, flush=True)
            time.sleep(2)
    raise RuntimeError("gave up")


def ac(path, q):
    items = json.loads(req(path + "?q=" + urllib.parse.quote(q)))
    return [(x["value"], re.search(r'data-id="([^"]*)"', x["label"]).group(1)) for x in items]


page = req("/disconnection/detailed")
form = page[page.index('id="disconnection-detailed-search-form"'):]
fbid = re.search(r'name="form_build_id" value="([^"]+)"', form).group(1)
city = ac("/disconnection/detailed/autocomplete/read_city", "Вінн")[0]
street = [s for s in ac("/disconnection/detailed/autocomplete/read_street/" + city[1], "1-й Ботан")][0]
houses = ac("/disconnection/detailed/autocomplete/read_house/" + street[1], "2")
print(city, street, houses, file=log, flush=True)
house = next(h for h in houses if h[0] == "2")

data = urllib.parse.urlencode({
    "search_type": "0", "city": city[0], "city_id": city[1], "street": street[0], "street_id": street[1],
    "house": house[0], "house_id": house[1], "form_build_id": fbid, "form_id": "disconnection_detailed_search_form",
    "_triggering_element_name": "search", "_triggering_element_value": "Показати", "_drupal_ajax": "1",
}).encode()
raw = req("/disconnection/detailed?ajax_form=1&_wrapper_format=drupal_ajax", data)
open(OUT + ".json", "w", encoding="utf-8").write(raw)
html = next(c["data"] for c in json.loads(raw) if c.get("command") == "insert")
open(OUT + ".html", "w", encoding="utf-8").write(html)
print("saved", len(html), file=log, flush=True)
