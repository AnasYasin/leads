#!/usr/bin/env python3
"""arbeitnow public job-board API.

Written 5 Sep 2026 evening, as the 5 Sep morning note in instructions/COMPANIES.md asked for. That
run read this source by hand and every one of its four sent jobs came from it, so it is
worth a script.

`https://www.arbeitnow.com/api/job-board-api?page=N` returns ~175 server-rendered jobs a
page with the full description inline. No user-agent trick, no JavaScript, no 403.

Two traps, both recorded on 5 Sep 2026 morning and both handled here:

- **`created_at` is arbeitnow's ingest date, not the employer's posting date**, and the
  gap runs to two months (Finom read 4 Sep here against 6 Jul on Finom's own Lever board).
  It is emitted as `ingest_date`, never as `date`, so nothing downstream can mistake it
  for a posting date and hand out a freshness bonus on it. Re-date at source.
- **The feed interleaves German, UK and Irish jobs.** The `location` field alone does not
  separate them, so rows whose `url` host is not `arbeitnow.com` are dropped here.
"""
import json, re, sys, urllib.parse, urllib.request
import concurrent.futures as cf

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json"}
PAGES = 14


import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from textclean import html_to_text  # noqa: E402
KEEP_RAW = bool(_os.environ.get("RADAR_KEEP_RAW"))   # keep the source HTML as desc_raw, for comparisons


# arbeitnow ends every description with a link to itself. It is not part of the posting, and its
# words ("English Speaking Jobs in Germany") were quoted as the posting's language line.
FOOTER = re.compile(r"\s*(?:Find )?(?:more )?(?:English Speaking )?Jobs in Germany on Arbeitnow\s*$")


def page(n):
    url = "https://www.arbeitnow.com/api/job-board-api?page=%d" % n
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=45) as r:
            return n, json.loads(r.read().decode("utf-8", "replace")).get("data") or [], None
    except Exception as e:
        return n, [], str(e)[:80]


rows, errs = [], []
with cf.ThreadPoolExecutor(max_workers=6) as ex:
    for n, data, err in ex.map(page, range(1, PAGES + 1)):
        if err:
            errs.append((n, err))
        print("page %-3d -> %d %s" % (n, len(data), err or ""), file=sys.stderr)
        rows.extend(data)

out, seen, skipped_host = [], set(), 0
for j in rows:
    url = j.get("url") or ""
    # German feed only; .co.uk rows are interleaved and location alone will not tell them apart
    host = urllib.parse.urlparse(url).netloc.lower()
    if not host.endswith("arbeitnow.com"):
        skipped_host += 1
        continue
    slug = j.get("slug") or url
    if slug in seen:
        continue
    seen.add(slug)
    out.append({
        "title": j.get("title") or "",
        "company": j.get("company_name") or "",
        "location": j.get("location") or "",
        "url": url,
        # deliberately NOT "date": this is arbeitnow's ingest timestamp, not the posting date
        "ingest_date": str(j.get("created_at") or ""),
        "date": "",
        "remote": bool(j.get("remote")),
        "tags": ",".join(j.get("tags") or [])[:200],
        # 2 Oct 2026: the whole text, cleaned. It was flattened to one line and cut at 12,000.
        "desc": FOOTER.sub("", html_to_text(j.get("description") or "")).strip(),
        "source": "arbeitnow",
    })
    if KEEP_RAW:
        out[-1]["desc_raw"] = j.get("description") or ""

json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False)
print("TOTAL %d raw, %d after host filter + dedupe (%d non-.com dropped), %d page errors"
      % (len(rows), len(out), skipped_host, len(errs)), file=sys.stderr)
