#!/usr/bin/env python3
"""The date the employer's own board gives a job, which is the only date worth trusting.

LinkedIn and XING cards carry the date the aggregator listed or re-listed the job, not the day
the employer opened it. On 8 Sep 2026 the radar sent MEDIFOX DAN as "posted 2026-09-07" from a
LinkedIn card while the employer's Workday page said 28 August, and Audatic's two roles as
7-hour-old cards while Sonova's board had carried them since 12 and 13 August. The freshness
bonus, and his decision to chase a referral fast, both hang on this number.

    true_date(url, title) -> (iso_date or "", note)

Reads the board through `deepdive.py` when the url is a known ATS (Personio, Greenhouse, Ashby,
Lever, Recruitee, Workable, SmartRecruiters, Teamtailor, Workday), matching the job by id in
the url first and by title second. For any other page it looks for a JSON-LD JobPosting
`datePosted`. Returns "" when nothing is found; never guesses.
"""
import json, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deepdive

UA = deepdive.UA


def _jsonld_date(url):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            t = r.read(1500000).decode("utf-8", "replace")
    except Exception as e:
        return "", "page fetch failed (%s)" % str(e)[:40]
    for m in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', t, re.S | re.I):
        try:
            d = json.loads(m)
        except Exception:
            continue
        for c in (d if isinstance(d, list) else [d]):
            if isinstance(c, dict) and c.get("@type") == "JobPosting" and c.get("datePosted"):
                return str(c["datePosted"])[:10], "JSON-LD datePosted on the page"
    m = re.search(r'"datePosted"\s*:\s*"(\d{4}-\d{2}-\d{2})', t)
    if m:
        return m.group(1), "datePosted in page data"
    # SuccessFactors (jobs.sonova.com and the like): <meta itemprop="datePosted" content="Wed Aug 12 02:01:00 UTC 2026">
    m = re.search(r'itemprop="datePosted"\s+content="([^"]+)"', t)
    if m:
        d = _any_date(m.group(1))
        if d:
            return d, "itemprop datePosted on the page"
    # SuccessFactors and similar pages print the date next to a label, e.g. "Date: Aug 12, 2026"
    # or "Veröffentlicht am 12.08.2026". Only accept a date within 60 characters of such a label.
    txt = re.sub(r"<[^>]+>", " ", t)
    m = re.search(r"(?:Date|Posted|Published|Ver(?:ö|oe)ffentlicht|Online seit|Eingestellt)[^0-9A-Za-z]{0,20}"
                  r"(?:[A-Za-z]{0,12}\s*){0,3}?(\d{1,2})[./ ]\s*(\d{1,2}|[A-Za-zä]{3,9})[./, ]\s*(\d{4})", txt)
    if m:
        d = _parse_date(m.group(1), m.group(2), m.group(3))
        if d:
            return d, "date next to a label on the page"
    m = re.search(r"(?:Date|Posted|Published)[^0-9A-Za-z]{0,20}([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})", txt)
    if m:
        d = _parse_date(m.group(2), m.group(1), m.group(3))
        if d:
            return d, "date next to a label on the page"
    return "", "no JSON-LD date on the page"


def _any_date(txt):
    import datetime
    txt = txt.strip()
    for fmt in ("%a %b %d %H:%M:%S %Z %Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d.%m.%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.datetime.strptime(txt[:len(txt)], fmt).date().isoformat()
        except Exception:
            pass
    m = re.match(r"(\d{4}-\d{2}-\d{2})", txt)
    if m:
        return m.group(1)
    m = re.search(r"([A-Za-z]{3})\s+(\d{1,2})\D+(\d{4})", txt)
    return _parse_date(m.group(2), m.group(1), m.group(3)) if m else ""


MONTHS = {"jan": 1, "feb": 2, "mar": 3, "mär": 3, "apr": 4, "may": 5, "mai": 5, "jun": 6, "jul": 7,
          "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dec": 12, "dez": 12}


def _parse_date(day, month, year):
    try:
        mo = int(month) if month.isdigit() else MONTHS.get(month[:3].lower())
        if not mo:
            return ""
        import datetime
        yr = int(year)
        # 3 Oct 2026: a Delivery Hero careers page yielded year 1, which rendered as
        # "posted 0001-01-01 ... RELISTED 739845 days later". Reject implausible years.
        if yr < 2000 or yr > datetime.date.today().year + 1:
            return ""
        return datetime.date(yr, mo, int(day)).isoformat()
    except Exception:
        return ""


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def true_date(url, title=""):
    if not url:
        return "", "no url"
    kind, slug = deepdive.detect(url)
    if not kind:
        return _jsonld_date(url)
    try:
        jobs = (deepdive.workday(slug, url) if kind == "workday" else
                deepdive.successfactors(slug, title, pages=2) if kind == "successfactors" else deepdive.READERS[kind](slug))
    except Exception as e:
        return "", "%s board error %s" % (kind, str(e)[:40])
    if not jobs:
        d, note = _jsonld_date(url)
        return (d, note) if d else ("", "%s board returned no roles, %s" % (kind, note))
    # Ashby job urls carry a uuid, not a numeric id, so a digits-only match fell
    # through to the title match and picked the wrong row whenever a board held the
    # same title more than once (Nexxa.AI, 23 September 2026: three "Applied AI
    # Engineer" posts, Munich redated to the Bay Area one).
    ids = re.findall(r"(\d{5,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", url)
    for j in jobs:
        if j.get("date") and ids and any(i in (j.get("url") or "") for i in ids):
            return j["date"], "%s board, matched by id" % kind
    nt = _norm(title)
    if nt:
        best = None
        for j in jobs:
            jt = _norm(j.get("title"))
            if jt and (jt == nt or jt in nt or nt in jt):
                best = j
                break
        if best and best.get("date"):
            return best["date"], "%s board, matched by title" % kind
    if kind == "workday" and jobs[0].get("date"):
        return jobs[0]["date"], "workday posting"
    d, note = _jsonld_date(url)
    return (d, note) if d else ("", "%s board reachable, job not matched, %s" % (kind, note))


if __name__ == "__main__":
    print(true_date(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""))
