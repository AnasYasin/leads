#!/usr/bin/env python3
"""LinkedIn jobs, through the public guest endpoint. No login, no JavaScript.

Verified 8 Sep 2026 from the candidate's laptop. The old `site:linkedin.com/jobs` web-search sweep
returned category index pages for five runs running and was written off. This endpoint is a
different thing: it is what the logged-out linkedin.com/jobs page itself calls to load cards.

    https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
        ?keywords=<role>&location=<place>&f_TPR=r86400&start=<0,10,20..>  (10 cards a page)

- `f_TPR=r86400` keeps only jobs posted in the last 24 hours. `r3600` is one hour, `r604800`
  a week. This is the whole point of the source: he wants roles hours old, so he can reach
  people at the company before the pool grows.
- Each card carries the title, company, location, an ISO `datetime` and the numeric job id
  (`urn:li:jobPosting:<id>`). The id is the key for `read_linkedin.py`, which fetches the
  full description from `/jobs-guest/jobs/api/jobPosting/<id>`.
- LinkedIn pads thin result sets with looser matches, so a page of 25 cards is not evidence
  of 25 real matches. `filter_run.py` applies the title filter; do not trust counts here.
- The full Chrome user-agent string matters. A bare one gets a 999 or an empty body.
- A 429 means slow down, not that the source is dead. Back off and retry once.

Usage: collect_linkedin.py <out.json> [hours]   (hours defaults to 24)
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9,de;q=0.8"}

import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import cfg  # noqa: E402
# Search terms live in config/radar.yaml (search.linkedin) since 29 Sep 2026. `targets` are
# company-targeted queries with their own window in hours (a referral company's rare roles).
ROLES = cfg.get("search", "linkedin", "roles")
PLACES = cfg.get("search", "linkedin", "places")
TARGETS = [(t["query"], t["place"], t["hours"]) for t in cfg.get("search", "linkedin", "targets")]
# The guest endpoint returns 10 cards a page and `start` is a card offset (start=10 is page 2).
# Until 9 Oct 2026 this stepped 25 and stopped on any page under 25 cards, so every query
# ended after page 1: about 100 of the ~1,100 Germany 24h cards a day were ever seen.
PAGE = 10
MAX_PAGES = 80           # 'applied scientist', Germany, 24h ran to 77 pages on 9 Oct 2026
STALE_PAGES = 3          # stop after this many pages in a row with no card new to the query
TIME_BUDGET = 1200        # seconds; collect_all.py kills a collector at 1500, so stop early and keep the rows
TARGET_PAGES = 3         # company-targeted queries (week window) stay shallow; deeper is padding
PAUSE = 0.8              # 640 calls at 0.8 s gave no 429 on 9 Oct 2026

CARD = re.compile(r'data-entity-urn="urn:li:jobPosting:(\d+)"(.*?)(?=data-entity-urn=|\Z)', re.S)
TITLE = re.compile(r'base-search-card__title">\s*(.*?)\s*<', re.S)
COMPANY = re.compile(r'base-search-card__subtitle">\s*(?:<a[^>]*>)?\s*(.*?)\s*<', re.S)
LOC = re.compile(r'job-search-card__location">\s*(.*?)\s*<', re.S)
DATE = re.compile(r'<time[^>]*datetime="([^"]+)"')
URL = re.compile(r'href="(https://[^"?]+)')


def fetch(url, tries=2):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 429 and i + 1 < tries:
                time.sleep(20)
                continue
            return e.code, ""
        except Exception as e:
            if i + 1 < tries:
                time.sleep(5)
                continue
            return -1, str(e)[:80]
    return -1, ""


def parse(body):
    out = []
    for jid, chunk in CARD.findall(body):
        t, c, l, d, u = (TITLE.search(chunk), COMPANY.search(chunk), LOC.search(chunk),
                         DATE.search(chunk), URL.search(chunk))
        out.append({
            "li_id": jid,
            "title": html.unescape(t.group(1)).strip() if t else "",
            "company": html.unescape(c.group(1)).strip() if c else "",
            "location": html.unescape(l.group(1)).strip() if l else "",
            "date": d.group(1) if d else "",
            "url": u.group(1) if u else "https://www.linkedin.com/jobs/view/%s" % jid,
            "desc": "", "source": "linkedin",
        })
    return out


def main():
    out_path = sys.argv[1]
    hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    rows, seen, errs, calls = [], set(), [], 0
    t0, out_of_time = time.time(), False
    plan = [(r, p, hours, MAX_PAGES) for r in ROLES for p in PLACES] + \
           [(q, p, h, TARGET_PAGES) for q, p, h in TARGETS]
    for role, place, hrs, max_pages in plan:
        if True:
            new_here, stale, mine = 0, 0, set()
            for page in range(max_pages):
                if time.time() - t0 > TIME_BUDGET:
                    out_of_time = True
                    break
                q = urllib.parse.urlencode({"keywords": role, "location": place,
                                            "f_TPR": "r%d" % (hrs * 3600), "start": page * PAGE})
                code, body = fetch("https://www.linkedin.com/jobs-guest/jobs/api/"
                                   "seeMoreJobPostings/search?" + q)
                calls += 1
                if code != 200:
                    errs.append((role, place, page * PAGE, code))
                    break
                cards = parse(body)
                if not cards:
                    break
                added, fresh_here = 0, 0
                for c in cards:
                    if c["li_id"] not in mine:
                        mine.add(c["li_id"])
                        fresh_here += 1
                    if c["li_id"] not in seen:
                        seen.add(c["li_id"])
                        c["query"] = role
                        rows.append(c)
                        added += 1
                new_here += added
                # Stale means no card new to THIS query. Related queries share their top cards,
                # so counting against all queries stopped 'AI engineer' after 3 pages at 0 new.
                stale = 0 if fresh_here else stale + 1
                if stale >= STALE_PAGES:
                    break
                time.sleep(PAUSE)
            print("%-28s %-8s -> %3d new (calls so far %d)" % (role, place, new_here, calls),
                  file=sys.stderr)
            # Written after every query: collect_all.py kills a collector at 1500 s, and the
            # deeper paging (about 700 calls) runs close to that. A kill keeps what was found.
            json.dump(rows, open(out_path, "w"), ensure_ascii=False, indent=1)
            time.sleep(PAUSE)
    json.dump(rows, open(out_path, "w"), ensure_ascii=False, indent=1)
    if out_of_time:
        print("TIME BUDGET %d s reached, later queries were cut short" % TIME_BUDGET, file=sys.stderr)
    print("TOTAL %d unique LinkedIn jobs in last %dh, %d calls, %d s, %d errors %s"
          % (len(rows), hours, calls, time.time() - t0, len(errs), errs[:5]), file=sys.stderr)


if __name__ == "__main__":
    main()
