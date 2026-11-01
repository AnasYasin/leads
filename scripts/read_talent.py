#!/usr/bin/env python3
"""Fetch full descriptions for talent.com candidates.

The single most useful thing found on 15 August 2026: `de.talent.com/view?id=<id>`
is server-rendered and carries the **whole job description**, not a teaser. That
moves talent.com out of the Tier 2 "harvest a company name, then go and read the
role at source" workflow and into Tier 1 — one fetch per job, full text, scoreable
immediately. It is the first aggregator on this radar that does not need the
find-the-real-board dance in section 3 of instructions/PROMPT.md.

Two things to watch:
- The page says "Diese Stelle ist in deinem Land nicht verfügbar" on some rows.
  That is a geo notice on the *apply* button, not a closed posting — the
  description is still there below it. Do not read it as expired.
- The description ends where the related-jobs rail begins; cut at the German
  boilerplate ("Ähnliche Stellenangebote", "Erstelle einen Job-Alert") so the
  scoring text is not polluted with other companies' titles.

Usage: read_talent.py <scratchdir> [<substring> ...]
"""
import concurrent.futures as cf
import json
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from trim_desc import trim
from textclean import html_to_text
import os
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"}

# 29 Sep 2026: importable, so scripts/fetch_desc.py can reuse one() without the command line.
needles = []

START = re.compile(r"Stellenbeschreibung", re.I)
# `Jobalert für diese Suche erstellen` is the real boundary — it opens the related-jobs
# rail, which carries a dozen *other* companies' adverts in full. Missing it on the first
# pass (15 Aug 2026) made every German-language requirement in the rail look like it
# belonged to the job being scored: Kärcher, WetterOnline, Nulegal and credium all showed
# phantom "sehr gute Deutschkenntnisse (C1)" hits that were actually XITASO's and PTA's.
# Any language or seniority check run past this point is reading someone else's job.
END = re.compile(r"Jobalert für diese Suche erstellen|Ähnliche Stellenangebote|"
                 r"Erstelle einen Job-Alert|Ähnliche Stellen\b|Beliebte Suchanfragen|"
                 r"Ähnliche Jobs|Job-Alert erstellen|Verwandte Jobs", re.I)


def text(h):
    # 2 Oct 2026: one cleaner for every source (scripts/textclean.py). Line breaks are kept.
    return html_to_text(h)


def one(j):
    key = ("%s | %s" % (j["company"], j["title"])).lower()
    if needles and not any(n in key for n in needles):
        return None
    out = dict(j)
    try:
        req = urllib.request.Request(j["url"], headers=UA)
        with urllib.request.urlopen(req, timeout=45) as r:
            t = text(r.read().decode("utf-8", "replace"))
        m = START.search(t)
        body = t[m.end():] if m else t
        e = END.search(body)
        if e:
            body = body[:e.start()]
        # 29 Sep 2026: benefits and boilerplate trimmed; pay, language and location lines are kept.
        out["desc"], out["desc_cut"] = trim(body.strip())
        out["ok"] = bool(out["desc"])
    except Exception as ex:
        out["desc"], out["ok"], out["err"] = "", False, str(ex)[:120]
    return out


if __name__ == "__main__":
    SCRATCH = sys.argv[1]
    needles = [n.lower() for n in sys.argv[2:]]
    cands = json.load(open(os.path.join(SCRATCH, "candidates.json")))
    rows = [r for r in (map(one, cands)) if r] if False else None
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        rows = [r for r in ex.map(one, cands) if r]

    json.dump(rows, open(os.path.join(SCRATCH, "talent_read.json"), "w"),
              ensure_ascii=False, indent=1)
    for r in rows:
        print("%-28s | %-52s | %5d chars %s"
              % (r["company"][:28], r["title"][:52], len(r["desc"]),
                 r.get("err", "")), file=sys.stderr)
    print("read %d" % len(rows), file=sys.stderr)
