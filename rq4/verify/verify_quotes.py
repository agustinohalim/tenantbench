"""Check each RQ4 quote against the live page text (tags stripped, whitespace and quotes normalised)."""
import html, json, pathlib, re, sys, urllib.request
HERE = pathlib.Path(__file__).parent
def norm(s):
    s = html.unescape(s)
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("​", "")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).lower()
cache, out = {}, []
for spec, url, q in json.loads((HERE / "quotes.json").read_text()):
    if url not in cache:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research doc check)"})
            raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
            txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
            # two renderings: tags as spaces (prose) and tags removed (code blocks split into spans)
            cache[url] = norm(re.sub(r"<[^>]+>", " ", txt)) + " ||| " + norm(re.sub(r"<[^>]+>", "", txt))
        except Exception as e:  # noqa: BLE001
            cache[url] = None; print("FETCHFAIL", url, e, file=sys.stderr)
    t = cache[url]
    st = "fetch-fail" if t is None else ("FOUND" if norm(q) in t else "NOT-FOUND")
    out.append({"spec": spec, "url": url, "quote": q, "status": st})
    print(st, spec, q[:60], url)
(HERE / "verify_result.json").write_text(json.dumps(out, indent=1))
