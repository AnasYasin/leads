#!/usr/bin/env python3
"""Getro VC portfolio boards. Page size is fixed at 20 regardless of hitsPerPage."""
import datetime
import json
import re
import sys
import urllib.request
import concurrent.futures as cf

HDR = {"Accept": "application/json", "Content-Type": "application/json",
       "User-Agent": "Mozilla/5.0"}
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import cfg  # noqa: E402
# VC collections live in config/radar.yaml (search.getro) since 29 Sep 2026.
COLLECTIONS = [(c["id"], c["name"]) for c in cfg.get("search", "getro", "collections")]


def iso(ts):
    """Getro's `created_at` is epoch seconds (29 Oct 2026: 5,184 of 5,184 rows). It was stored as the
    bare digits since 5 Aug 2026, so prescore.py read every Getro row as undated, put it in the last
    reading group with the -2 penalty, and 7 rows were sent in 12 weeks. 555 of the rows that morning
    were under a week old."""
    try:
        return datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return str(ts)[:10] if re.match(r"\d{4}-\d\d-\d\d", str(ts or "")) else ""


def page(cid, p):
    body = json.dumps({"hitsPerPage": 100, "page": p}).encode()
    req = urllib.request.Request(
        "https://api.getro.com/api/v2/collections/%d/search/jobs" % cid,
        data=body, headers=HDR, method="POST")
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def one(c):
    cid, name = c
    jobs, p, err = [], 0, None
    try:
        while p < 160:
            d = page(cid, p)
            res = (d.get("results") or {}).get("jobs") or []
            if not res:
                break
            for j in res:
                org = j.get("organization") or {}
                locs = j.get("locations") or []
                loc = ", ".join(l.get("name", "") for l in locs if isinstance(l, dict)) \
                    if locs and isinstance(locs[0], dict) else ", ".join(map(str, locs))
                jobs.append(dict(title=j.get("title", ""), company=org.get("name", ""),
                                 location=loc, url=j.get("url", ""),
                                 date=iso(j.get("created_at")),
                                 desc="", source="getro:" + name,
                                 org_url=org.get("website_url", "") or "",
                                 org_desc=(org.get("description") or "")[:300]))
            p += 1
    except Exception as e:
        err = str(e)[:80]
    return name, jobs, err


def main(out):
    all_jobs, rep = [], []
    with cf.ThreadPoolExecutor(max_workers=5) as ex:
        for name, jobs, err in ex.map(one, COLLECTIONS):
            rep.append(dict(board=name, n=len(jobs), err=err))
            all_jobs.extend(jobs)
            print("%-20s %5d %s" % (name, len(jobs), err or ""), file=sys.stderr)

    # dedupe on url
    seen, ded = set(), []
    for j in all_jobs:
        u = (j["url"] or "").rstrip("/")
        if u and u in seen:
            continue
        seen.add(u)
        ded.append(j)
    json.dump(ded, open(out, "w"), ensure_ascii=False)
    print("TOTAL %d, %d after url dedupe" % (len(all_jobs), len(ded)), file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1])
