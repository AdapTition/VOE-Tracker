"""Fetch /disconnection and /disconnection/planned, dump table rows as text."""
import html, re, sys, time, urllib.request, urllib.error

BASE = "https://www.voe.com.ua"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"
outdir = sys.argv[1]


def get(path):
    for i in range(6):
        try:
            r = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
            return urllib.request.urlopen(r, timeout=40).read().decode("utf-8")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            time.sleep(2)
    raise RuntimeError(path)


def text(s):
    s = re.sub(r"<br\s*/?>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


for name, path in [("disconnection", "/disconnection"), ("planned", "/disconnection/planned")]:
    page = get(path)
    open(f"{outdir}/{name}.html", "w", encoding="utf-8").write(page)
    with open(f"{outdir}/{name}.rows.txt", "w", encoding="utf-8") as f:
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, flags=re.S):
            cells = [text(c)[:300] for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)]
            f.write(" | ".join(cells) + "\n")
