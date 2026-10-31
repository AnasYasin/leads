#!/usr/bin/env python3
"""StepStone, from the cloud only. The laptop gets a 403; the cloud sandbox gets the real page.

Verified 8 Sep 2026 with three probe routines:
- listing `https://www.stepstone.de/jobs/<role-slug>/in-<city>?sort=2&ag=age_7` answers 200 with
  ~1.2 MB and 25 `<article data-at="job-item">` cards, each linking to
  `/stellenangebote--<Title>-<City>-<Company>--<id>-inline.html` and to the company page
  `/cmp/de/<company>-<id>/jobs`. The page state holds a `datePosted` per item.
- the job page (570 KB) carries one JSON-LD JobPosting: title, hiringOrganization, jobLocation,
  datePosted, validThrough, employmentType, description, url. That is the source of truth here;
  the listing only supplies the links.
- `ag=age_7` is "newer than 7 days", `ag=age_1` is 24 hours. Seven days plus the seen check
  keeps the twice-daily runs from missing anything; the date filter below trims the rest.

Usage: collect_stepstone.py <out.json> [days]     (days defaults to 3)
"""
import datetime, html, json, re, sys, time, urllib.parse, urllib.request
import concurrent.futures as cf

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"}
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import cfg  # noqa: E402
# Role slugs and cities live in config/radar.yaml (search.stepstone) since 29 Sep 2026.
ROLES = cfg.get("search", "stepstone", "roles")
CITIES = cfg.get("search", "stepstone", "cities")
# 7 Oct 2026: was 300, which left about 250 of ~550 links unread every run, always from the roles
# listed last. Reading all of them takes a few minutes in the cloud, well inside collect_all's 1500 s.
MAX_JOB_FETCH = 1000
LINK = re.compile(r'href="((?:https://www\.stepstone\.de)?/stellenangebote--[^"]+?--(\d+)-inline\.html)')


def fetch(url, timeout=45):
    # 7 Oct 2026: some job links carry invisible characters (U+200D, U+00AD) that urllib cannot send.
    url = urllib.parse.quote(url, safe=":/?&=%#+")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from textclean import html_to_text  # noqa: E402
KEEP_RAW = bool(_os.environ.get("RADAR_KEEP_RAW"))   # keep the source HTML as desc_raw, for comparisons


def jsonld_job(page):
    for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            d = json.loads(m)
        except Exception:
            continue
        cands = d if isinstance(d, list) else [d]
        for c in cands:
            if isinstance(c, dict) and c.get("@type") == "JobPosting":
                return c
    return None


def loc_of(jl):
    if isinstance(jl, list):
        return ", ".join(x for x in (loc_of(j) for j in jl) if x)
    if isinstance(jl, dict):
        a = jl.get("address") or {}
        if isinstance(a, dict):
            return ", ".join(x for x in [a.get("addressLocality"), a.get("addressRegion")] if x)
    return ""


def detail(row):
    try:
        st, page = fetch(row["url"])
    except Exception as e:
        row["error"] = str(e)[:80]
        return row
    j = jsonld_job(page)
    if not j:
        row["error"] = "no JSON-LD JobPosting"
        return row
    org = j.get("hiringOrganization") or {}
    row["title"] = j.get("title") or row.get("title", "")
    row["company"] = (org.get("name") if isinstance(org, dict) else str(org)) or ""
    row["location"] = loc_of(j.get("jobLocation")) or row.get("location", "")
    row["date"] = (j.get("datePosted") or "")[:10]
    row["valid_through"] = (j.get("validThrough") or "")[:10]
    row["employment"] = j.get("employmentType") or ""
    row["direct_apply"] = bool(j.get("directApply"))
    row["desc"] = html_to_text(j.get("description") or "")      # whole text, no cut (2 Oct 2026)
    if KEEP_RAW:
        row["desc_raw"] = j.get("description") or ""
    # baseSalary is a standard JSON-LD JobPosting field. Whether StepStone fills it could not
    # be checked from the laptop, which gets a 403 here, so this is written to cost nothing when
    # the field is absent. The description is read for a band either way.
    bs = j.get("baseSalary") or {}
    val = bs.get("value") if isinstance(bs, dict) else None
    if isinstance(val, dict):
        lo, hi = val.get("minValue"), val.get("maxValue")
        unit = (val.get("unitText") or "").upper()
        cur = bs.get("currency") or "EUR"
        if lo and hi:
            row["salary"] = "%s %s-%s%s" % (cur, lo, hi, " an hour" if unit == "HOUR" else
                                            " a month" if unit == "MONTH" else "")
        elif val.get("value"):
            row["salary"] = "%s %s" % (cur, val["value"])
    return row


def main():
    out_path = sys.argv[1]
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    rows, seen, errs = [], set(), []
    for role in ROLES:
        for city in CITIES:
            path = "/jobs/%s" % role if city == "deutschland" else "/jobs/%s/in-%s" % (role, city)
            url = "https://www.stepstone.de%s?sort=2&ag=age_7" % path
            try:
                st, page = fetch(url)
            except Exception as e:
                errs.append((role, city, str(e)[:60]))
                continue
            new = 0
            for href, jid in LINK.findall(page):
                if jid in seen:
                    continue
                seen.add(jid)
                full = href if href.startswith("http") else "https://www.stepstone.de" + href
                slug = href.split("/stellenangebote--", 1)[1].rsplit("--", 1)[0]
                rows.append({"ss_id": jid, "url": full, "title": slug.replace("-", " "),
                             "company": "", "location": city, "date": "", "desc": "",
                             "source": "stepstone", "query": role})
                new += 1
            print("%-26s %-12s -> %3d new (page %d KB)" % (role, city, new, len(page) // 1024),
                  file=sys.stderr)
            time.sleep(0.8)
    rows = rows[:MAX_JOB_FETCH]
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(detail, rows))
    fresh = [r for r in rows if not r.get("error") and (r.get("date") or "9999") >= cutoff]
    json.dump(fresh, open(out_path, "w"), ensure_ascii=False, indent=1)
    print("TOTAL %d links, %d read, %d within %d days, %d detail errors, %d listing errors %s"
          % (len(seen), sum(1 for r in rows if not r.get("error")), len(fresh), days,
             sum(1 for r in rows if r.get("error")), len(errs), errs[:3]), file=sys.stderr)


if __name__ == "__main__":
    main()
