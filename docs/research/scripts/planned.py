"""Submit the planned-outages form (year/month/region) and dump result rows."""
import html, http.cookiejar, re, sys, time, urllib.parse, urllib.request, urllib.error

BASE = "https://www.voe.com.ua"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"
outdir, year, month = sys.argv[1], sys.argv[2], sys.argv[3]
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
log = open(f"{outdir}/planned.log", "w", encoding="utf-8")


def req(path, data=None):
    for i in range(6):
        t0 = time.time()
        try:
            r = urllib.request.Request(BASE + path, data=data, headers={"User-Agent": UA})
            body = op.open(r, timeout=60).read().decode("utf-8")
            print(f"200 {time.time()-t0:.1f}s {path}", file=log, flush=True)
            return body
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            print(f"ERR {e} {path}", file=log, flush=True)
            time.sleep(2)
    raise RuntimeError(path)


def text(s):
    s = re.sub(r"<br\s*/?>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


page = req("/disconnection/planned")
form = page[page.index('id="disconnection-search-form"'):]
form = form[:form.index("</form>")]
fbid = re.search(r'name="form_build_id" value="([^"]+)"', form).group(1)
sel = re.search(r'name="region".*?</select>', form, flags=re.S).group(0)
regions = [(v, text(t)) for v, t in re.findall(r'<option value="([^"]+)"[^>]*>(.*?)</option>', sel, flags=re.S)]
print("regions:", regions, file=log, flush=True)
btn = re.search(r'name="op" value="([^"]*)"', form).group(1)

wanted = sys.argv[4:] or [regions[0][0]]
for region in wanted:
    data = urllib.parse.urlencode({"year": year, "month": month, "region": region, "form_build_id": fbid,
                                   "form_id": "disconnection_search_form", "op": btn}).encode()
    res = req("/disconnection/planned", data)
    open(f"{outdir}/planned_{region}.html", "w", encoding="utf-8").write(res)
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", res, flags=re.S):
        rows.append(" | ".join(text(c)[:400] for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)))
    open(f"{outdir}/planned_{region}.rows.txt", "w", encoding="utf-8").write("\n".join(rows))
    print(f"region {region}: {len(rows)} rows", file=log, flush=True)
