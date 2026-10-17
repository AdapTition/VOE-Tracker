"""Recon: how the street autocomplete matches different spellings."""
import json, re, sys, time, urllib.parse, urllib.request

BASE = "https://www.voe.com.ua/disconnection/detailed/autocomplete/read_street/510100000?q="
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"

sys.stdout = open(sys.argv[2], "w", encoding="utf-8")
for q in open(sys.argv[1], encoding="utf-8").read().splitlines():
    for i in range(5):
        try:
            r = urllib.request.Request(BASE + urllib.parse.quote(q), headers={"User-Agent": UA})
            items = json.loads(urllib.request.urlopen(r, timeout=40).read().decode())
            break
        except urllib.error.HTTPError as e:
            time.sleep(2)
    else:
        print(q, "-> FAILED"); continue
    print(f"{q!r} -> {len(items)}")
    for x in items:
        print("   ", x["value"], re.search(r'data-id="([^"]*)"', x["label"]).group(1))
