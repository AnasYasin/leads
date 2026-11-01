#!/usr/bin/env python3
"""Bundesagentur fuer Arbeit sweep. v6 search, v4 detail."""
import json
import sys
import time
import urllib.parse
import urllib.request

HDR = {"X-API-Key": "jobboerse-jobsuche", "User-Agent": "Mozilla/5.0"}
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import cfg  # noqa: E402
# Search terms and places live in config/radar.yaml (search.bundesagentur) since 29 Sep 2026.
QUERIES = cfg.get("search", "bundesagentur", "queries")
PLACES = [p or None for p in cfg.get("search", "bundesagentur", "places")]


def get(url, hdr=HDR, timeout=45):
    req = urllib.request.Request(url, headers=hdr)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# 2 Oct 2026 (docs/PROBLEMS.md 7.4): that morning the API was slow, searches timed out at 45 seconds each,
# and the run came back with 298 rows after 581 seconds where it normally brings 734 in 43. A failed
# search was dropped without a second try and without a count. Now the timeout is shorter, every failed
# search is tried once more at the end, and the last line says how many still failed.
TIMEOUT = 20
FAILED = []


def search(was, wo=None):
    p = {"was": was, "sort": "veroeffdatum", "size": "50"}
    if wo:
        p["wo"] = wo
        p["umkreis"] = "50"
    url = ("https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs?"
           + urllib.parse.urlencode(p))
    try:
        d = get(url, timeout=TIMEOUT)
    except Exception as e:
        print("FAIL %s wo=%s: %s" % (was, wo, e), file=sys.stderr)
        FAILED.append((was, wo))
        return []
    # v6: results live under `ergebnisliste`
    return d.get("ergebnisliste") or []


out, seenref = [], set()
PAIRS = [(q, wo) for q in QUERIES for wo in PLACES]
first = True
while PAIRS:
    todo, PAIRS = PAIRS, []
    for q, wo in todo:
        rows = search(q, wo)
        print("%-18s %-7s -> %d" % (q, wo or "DE", len(rows)), file=sys.stderr)
        for j in rows:
            ref = j.get("referenznummer")
            if not ref or ref in seenref:
                continue
            seenref.add(ref)
            locs = j.get("stellenlokationen") or []
            city = ""
            if locs:
                a = (locs[0] or {}).get("adresse") or {}
                city = ", ".join(x for x in [a.get("ort"), a.get("region")] if x)
            out.append({
                "ref": ref,
                "title": j.get("stellenangebotsTitel") or j.get("titel") or "",
                "company": j.get("firma") or "",
                "location": city,
                "beruf": j.get("hauptberuf") or "",
                "art": j.get("stellenangebotsart") or "",
                "date": j.get("datumErsteVeroeffentlichung") or "",
                "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/" + ref,
            })
        time.sleep(0.3)
    if first and FAILED:
        print("retrying %d failed searches" % len(FAILED), file=sys.stderr)
        PAIRS, FAILED[:] = list(FAILED), []
        time.sleep(5)
    first = False

json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
n_all = len(QUERIES) * len(PLACES)
if FAILED:
    print("SEARCHES FAILED after a retry: %d of %d (%s). The row count below is short." % (
        len(FAILED), n_all, "; ".join("%s/%s" % (q, wo or "DE") for q, wo in FAILED[:8])), file=sys.stderr)
print("TOTAL unique: %d%s" % (len(out), " (%d of %d searches failed)" % (len(FAILED), n_all) if FAILED else ""), file=sys.stderr)
