#!/usr/bin/env python3
"""de.talent.com sweep — the server-rendered replacement for the LinkedIn/XING/
Indeed/StepStone sweep, which has produced nothing usable for three runs.

Found working 15 August 2026 morning, after the 13 and 14 August notes flagged the
probe twice and it was not run. Two things matter and both are easy to get wrong:

- **The user-agent must be a full, realistic Chrome string.** With the abbreviated
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36" the site
  answers HTTP 200 with a 412KB JavaScript shell carrying zero job cards, which
  looks exactly like the JS-rendered dead end the other aggregators are. With the
  full AppleWebKit/KHTML string it answers 700KB of server-rendered HTML with 40
  cards. Same url, same status code, different body.
- **Use the query form `/jobs?k={role}&l={city}`, not the path form
  `/jobs/k-{role}-l-{city}`** that the 13 August note guessed at. The path form
  works but returns only 20 cards to the query form's 40.

Each card gives title, company, location and a relative "last updated" string.
That is enough to harvest a company name and go read the role at source, which is
the whole point of the aggregator tier. The logo url also leaks the feed's ATS
(`feedcode=join-ats`, `feedcode=greenhouse` ...), which is a free hint for
section 3's "find the real board" work.
"""
import concurrent.futures as cf
import json
import re
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"}

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import cfg  # noqa: E402
# Search terms live in config/radar.yaml (search.talent) since 29 Sep 2026.
ROLES = cfg.get("search", "talent", "roles")
CITIES = cfg.get("search", "talent", "cities")

CARD = re.compile(
    r'data-job-id="(?P<jid>[^"]+)".*?'
    r'(?:feedcode=(?P<feed>[^&"]+)&amp;company_name=[^"]*")?.*?'
    r'<h2 class="JobCard_title__[^"]*">(?P<title>.*?)</h2>.*?'
    r'<span class="JobCard_company__[^"]*">(?P<company>.*?)</span>.*?'
    r'<span class="JobCard_location__[^"]*">(?P<loc>.*?)</span>',
    re.S)
# "Zuletzt aktualisiert: vor 2 Tagen" sits in the sibling div just before the card.
AGE = re.compile(r'Zuletzt aktualisiert:\s*(?:vor\s*)?([^<]{1,40})<')


def strip(h):
    h = re.sub(r"<[^>]+>", "", h or "")
    for a, b in [("&amp;", "&"), ("&#x27;", "'"), ("&quot;", '"'), ("&nbsp;", " "),
                 ("&lt;", "<"), ("&gt;", ">"), ("&#39;", "'")]:
        h = h.replace(a, b)
    return re.sub(r"\s+", " ", h).strip()


# `date=1` keeps jobs updated in the last 24 hours and `p` pages through them (about 20 cards a
# page). Until 9 Oct 2026 neither was sent: each query read page 1 only, sorted by relevance, and
# 13 of its 20 cards were over 30 days old. Verified 9 Oct: date=1 pages 1-5 full, page 12 empty.
DATE_FILTER = "1"
MAX_PAGES = 10


def sweep(job):
    role, city = job
    out, seen_ids = [], set()
    for page in range(1, MAX_PAGES + 1):
        q = urllib.parse.urlencode({"k": role, "l": city, "date": DATE_FILTER, "p": page})
        url = "https://de.talent.com/jobs?" + q
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as r:
                h = r.read().decode("utf-8", "replace")
        except Exception as e:
            if page == 1:
                return role, city, [], str(e)[:80]
            break
        ages = AGE.findall(h)
        added = 0
        for i, m in enumerate(CARD.finditer(h)):
            if m.group("jid") in seen_ids:
                continue
            seen_ids.add(m.group("jid"))
            added += 1
            out.append(dict(
                title=strip(m.group("title")), company=strip(m.group("company")),
                location=strip(m.group("loc")), date="",
                age=strip(ages[i]) if i < len(ages) else "",
                feed=m.group("feed") or "",
                url="https://de.talent.com/view?id=" + m.group("jid"),
                desc="", source="talent.com", query="%s / %s" % (role, city)))
        if not added:
            break
    return role, city, out, None


all_jobs, report = [], []
with cf.ThreadPoolExecutor(max_workers=6) as ex:
    for role, city, jobs, err in ex.map(sweep, [(r, c) for r in ROLES for c in CITIES]):
        report.append(dict(role=role, city=city, n=len(jobs), err=err))
        all_jobs.extend(jobs)
        print("%-38s %-12s %3d %s" % (role[:38], city, len(jobs), err or ""),
              file=sys.stderr)

# Dedupe on company + normalised title; the same role comes back under many queries.
seen, ded = set(), []
for j in all_jobs:
    k = (j["company"].lower(), re.sub(r"[^a-z0-9]+", "", j["title"].lower()))
    if k in seen:
        continue
    seen.add(k)
    ded.append(j)

json.dump(ded, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
print("TOTAL %d, %d after company+title dedupe" % (len(all_jobs), len(ded)),
      file=sys.stderr)
