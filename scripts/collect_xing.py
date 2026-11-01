#!/usr/bin/env python3
"""XING jobs. Server-rendered search cards plus one detail fetch per card.

Verified 8 Sep 2026 from the candidate's laptop. The old `site:xing.com/jobs` web-search sweep
returned nothing for weeks; the site itself answers a plain fetch once redirects are
followed (`/jobs/search` 301s to a category url, keep `-L`).

Search cards carry the title, company and the job url, and nothing reliable about dates.
The job page carries what matters:
- `activatedAt`, the real posting timestamp
- `applyUrl`, the employer's own application link (the thing the candidate actually wants)
- `description` (HTML, escaped inside the page state), `companyName`, `location.city`,
  and a salary estimate.

So this collector fetches the detail for every card it keeps. Cards are few (about
10 to 16 a page), so that is cheap. XING ignores sort=date (measured 7 Oct 2026), so the page count is in config/radar.yaml.

Usage: collect_xing.py <out.json>
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import concurrent.futures as cf

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"}
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import cfg  # noqa: E402
# Search terms live in config/radar.yaml (search.xing) since 29 Sep 2026.
QUERIES = cfg.get("search", "xing", "queries")
PLACES = cfg.get("search", "xing", "places")
PAGES = cfg.get("search", "xing", "pages")

CARD = re.compile(r'<article[^>]*data-testid="job-search-result"[^>]*aria-label="([^"]*?)\.\s*Klicke[^"]*"(.*?)</article>', re.S)
LINK = re.compile(r'href="(/jobs/[^"]+-(\d{6,}))"')
COMPANY = re.compile(r'<img[^>]*title="([^"]*)"')


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from textclean import html_to_text, join_html  # noqa: E402
KEEP_RAW = bool(_os.environ.get("RADAR_KEEP_RAW"))   # keep the source HTML as desc_raw, for comparisons


def own_job(page, xing_id):
    """The page's own job as a dict, or None.

    A XING job page carries ten jobs in its state: the job itself and nine "similar jobs", each a
    `VisibleJob:<id>.<hash>` object with its own apply link, salary and company. Until 2 Oct 2026 this
    collector took the first `applyUrl`, the first `salary` and the first `companyName` anywhere in the
    page. When the job's own object had no apply link, the link of a similar job was stored: on 2 Oct an
    Oper posting was sent with the apply link of an Accenture job (docs/PROBLEMS.md 1.7). The salary was the
    first one in the page as well, and 42 of 284 rows had no company, because the company is under
    `companyNameOverride`, never `companyName`. Now only the object with this job's id is read."""
    m = re.search(r'"VisibleJob:%s\.[0-9a-f]+":\{' % re.escape(str(xing_id)), page)
    if not m:
        return None
    i = k = m.end() - 1
    depth, in_str, esc = 0, False, False
    while k < len(page):
        ch = page[k]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    try:
        return json.loads(page[i:k + 1])
    except ValueError:
        return None


def description_html(d):
    """The posting text as HTML. XING stores it in one of two shapes: `content`, one block of HTML, or
    a template with a title and a content field per section (company, tasks, profile, offer)."""
    if isinstance(d, str):
        return d
    if not isinstance(d, dict):
        return ""
    if d.get("content"):
        return d["content"]
    parts = [d.get("genericDescription")]
    for k, v in d.items():
        if k.endswith("Content") and v:
            parts.append((d.get(k[:-len("Content")] + "Title") or "", v))
    return join_html(*parts)


def ld_description(page):
    """The description in the page's own JobPosting block, for a shape this collector does not know."""
    for m in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        try:
            d = json.loads(m)
        except ValueError:
            continue
        for c in d if isinstance(d, list) else [d]:
            if isinstance(c, dict) and c.get("@type") == "JobPosting" and isinstance(c.get("description"), str):
                return c["description"]
    return ""


def detail(row):
    try:
        t = fetch(row["url"])
    except Exception as e:
        row["error"] = str(e)[:80]
        return row
    job = own_job(t, row.get("xing_id"))
    if job is None:
        # The page has no object for this job (a layout change). Nothing is guessed from the other
        # jobs on the page: the row keeps its card fields and says so.
        row["error"] = "the job's own data was not found on its page"
        row.setdefault("apply_url", "")
        row.setdefault("salary", "")
        return row
    row["date"] = job.get("activatedAt") or ""
    app = job.get("application") or {}
    row["apply_url"] = (app.get("applyUrl") or "").split("?utm_source")[0].split("&utm_source")[0]
    raw = description_html(job.get("description")) or ld_description(t)
    row["desc"] = html_to_text(raw)      # whole text, no cut (2 Oct 2026)
    if KEEP_RAW:
        row["desc_raw"] = raw
    info = job.get("companyInfo") or {}
    if not row.get("company"):
        row["company"] = info.get("companyNameOverride") or ""
    loc = job.get("location") or {}
    row["location"] = loc.get("city") or row.get("location", "")
    # XING shows a salary on most postings, and nearly all of them are its own estimate
    # (`SalaryEstimate`): 245 of 284 rows on 2 Oct, among them EUR 60,000 to 78,500 on a research
    # internship. An estimate is never a salary the posting states, so it is kept apart and never shown.
    sal = job.get("salary") or {}
    row["salary"] = ""
    if sal.get("minimum") and sal.get("maximum"):
        band = "%s-%s %s" % (sal["minimum"], sal["maximum"], sal.get("currency") or "EUR")
        if "estimate" in (sal.get("__typename") or "").lower():
            row["salary_estimate"] = band + " (XING's estimate, not from the posting)"
        else:
            row["salary"] = band
    return row


def main():
    rows, seen = [], set()
    for q in QUERIES:
        for place in PLACES:
            got = 0
            for p in range(1, PAGES + 1):
                url = ("https://www.xing.com/jobs/search?"
                       + urllib.parse.urlencode({"keywords": q, "location": place,
                                                 "sort": "date", "page": p}))
                try:
                    t = fetch(url)
                except Exception as e:
                    print("FAIL %s %s p%d: %s" % (q, place, p, e), file=sys.stderr)
                    break
                cards = CARD.findall(t)
                if not cards:
                    break
                for title, body in cards:
                    lk = LINK.search(body)
                    if not lk:
                        continue           # external partner card, no XING job page
                    jid = lk.group(2)
                    if jid in seen:
                        continue
                    seen.add(jid)
                    co = COMPANY.search(body)
                    rows.append({"xing_id": jid, "title": html.unescape(title).strip(),
                                 "company": html.unescape(co.group(1)).strip() if co else "",
                                 "location": place, "url": "https://www.xing.com" + lk.group(1),
                                 "date": "", "desc": "", "source": "xing", "query": q})
                    got += 1
                time.sleep(0.8)
            print("%-22s %-12s -> %3d new" % (q, place, got), file=sys.stderr)
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        rows = list(ex.map(detail, rows))
    json.dump(rows, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
    errs = sum(1 for r in rows if r.get("error"))
    dated = sum(1 for r in rows if r.get("date"))
    applies = sum(1 for r in rows if r.get("apply_url"))
    print("TOTAL %d XING jobs, %d with date, %d with employer apply url, %d detail errors"
          % (len(rows), dated, applies, errs), file=sys.stderr)


if __name__ == "__main__":
    main()
