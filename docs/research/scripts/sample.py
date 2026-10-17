"""Sample several Vinnytsia houses: status message + cell classes. Args: outdir, file with 'street_q|street_pick|house' lines."""
import json, re, sys, time, html as H, urllib.parse, urllib.request, urllib.error, http.cookiejar

BASE = "https://www.voe.com.ua"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"
outdir, listfile = sys.argv[1], sys.argv[2]
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
out = open(f"{outdir}/sample.txt", "w", encoding="utf-8")


def req(path, data=None):
    for i in range(6):
        try:
            r = urllib.request.Request(BASE + path, data=data, headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"})
            body = op.open(r, timeout=40).read().decode("utf-8")
            time.sleep(1)  # be gentle
            return body
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            time.sleep(3)
    raise RuntimeError(path)


def ac(path, q):
    items = json.loads(req(path + "?q=" + urllib.parse.quote(q)))
    return [(x["value"], re.search(r'data-id="([^"]*)"', x["label"]).group(1)) for x in items]


city = ("м.. Вінниця (Вінницька Область/М.Вінниця)", "510100000")
for line in open(listfile, encoding="utf-8").read().splitlines():
    sq, spick, hq = line.split("|")
    try:
        page = req("/disconnection/detailed")
        form = page[page.index('id="disconnection-detailed-search-form"'):]
        fbid = re.search(r'name="form_build_id" value="([^"]+)"', form).group(1)
        street = [s for s in ac("/disconnection/detailed/autocomplete/read_street/" + city[1], sq) if s[0] == spick][0]
        house = next(h for h in ac("/disconnection/detailed/autocomplete/read_house/" + street[1], hq) if h[0] == hq)
        data = urllib.parse.urlencode({
            "search_type": "0", "city": city[0], "city_id": city[1], "street": street[0], "street_id": street[1],
            "house": house[0], "house_id": house[1], "form_build_id": fbid, "form_id": "disconnection_detailed_search_form",
            "_triggering_element_name": "search", "_triggering_element_value": "Показати", "_drupal_ajax": "1",
        }).encode()
        doc = next(c["data"] for c in json.loads(req("/disconnection/detailed?ajax_form=1&_wrapper_format=drupal_ajax", data)) if c.get("command") == "insert")
        safe = re.sub(r"\W+", "_", f"{spick}_{hq}")
        open(f"{outdir}/{safe}.html", "w", encoding="utf-8").write(doc)
        msg = re.search(r'table-message">(.*?)</div>', doc, flags=re.S)
        msg = " / ".join(H.unescape(re.sub(r"<[^>]+>", "", p)).strip() for p in re.findall(r"<p[^>]*>(.*?)</p>", msg.group(1), flags=re.S)) if msg else ""
        cells = re.findall(r'class="disconnection-detailed-table-cell cell ([^"]*)"', doc)
        days = re.findall(r'day_col[^"]*">([^<]*)', doc)
        classes = {}
        for c in cells:
            k = " ".join(sorted(c.split()))
            classes[k] = classes.get(k, 0) + 1
        print(f"{spick} {hq}: days={days} classes={classes}\n    {msg[:260]}", file=out, flush=True)
    except Exception as e:
        print(f"{spick} {hq}: FAILED {e!r}", file=out, flush=True)
