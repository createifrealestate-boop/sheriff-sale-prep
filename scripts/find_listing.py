"""Find and download the current Sale Listings PDF from the Sheriff's site.

The filename changes with every update (e.g. November-Sale-List-Updated-10-20.pdf),
so the link is read off the page rather than guessed.

Usage: python3 -I find_listing.py OUT_DIR
Prints JSON: {"url":..., "file":..., "sha256":..., "page_modified":...}
Exit code 2 = site unreachable (domain not allowed / site down) -> tell the user, don't work around it.
"""
import hashlib, json, re, sys, urllib.request, urllib.error
from html.parser import HTMLParser
from pathlib import Path

PAGE = "https://sheriffalleghenycounty.com/sheriffs-sales/"
UA = {"User-Agent": "Mozilla/5.0 (sheriff-sale-prep)"}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self._href, self._text = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._text = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read(), r.headers


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    try:
        html, _ = get(PAGE)
    except (urllib.error.URLError, OSError) as e:
        print(json.dumps({"error": f"Could not reach {PAGE}: {e}"}))
        sys.exit(2)
    html = html.decode("utf-8", "replace")
    p = Links()
    p.feed(html)
    pdfs = [(h, t) for h, t in p.links if h.lower().split("?")[0].endswith(".pdf")]
    # prefer the link labelled "Sale Listings"; else any sale-list-looking PDF; skip the form packet
    pick = [h for h, t in pdfs if "sale listing" in t.lower()]
    pick += [h for h, t in pdfs if re.search(r"sale[-_ ]?list", h, re.I)]
    pick = [h for h in pick if "packet" not in h.lower()]
    if not pick:
        print(json.dumps({"error": "No Sale Listings PDF link found on the page", "pdf_links": pdfs}))
        sys.exit(3)
    url = urllib.request.urljoin(PAGE, pick[0])
    mod = re.search(r'"dateModified"\s*:\s*"([^"]+)"|article:modified_time"\s+content="([^"]+)"', html)
    try:
        data, _ = get(url)
    except (urllib.error.URLError, OSError) as e:
        print(json.dumps({"error": f"Could not download {url}: {e}"}))
        sys.exit(2)
    if not data.startswith(b"%PDF"):
        print(json.dumps({"error": "Downloaded file is not a PDF", "url": url}))
        sys.exit(3)
    name = Path(urllib.request.url2pathname(url.split("/")[-1].split("?")[0])).name
    f = out / name
    f.write_bytes(data)
    print(json.dumps({"url": url, "file": str(f), "sha256": hashlib.sha256(data).hexdigest(),
                      "page_modified": (mod.group(1) or mod.group(2)) if mod else None}))


if __name__ == "__main__":
    main()
