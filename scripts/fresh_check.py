#!/usr/bin/env python3
"""Every fresh job in his field must be read in the same run. Added 30 Sep 2026.

The radar is worth having because the candidate can apply to a job in his field on the day it is posted,
while the pool of applicants is still small. On 29 Sep the evening run read 67 jobs and left
Brainlab's Applied AI Engineer, statworx's ML Engineer and Apheris' Senior ML Engineer unread,
all posted that day and all in the candidate list after triage.

    python3 scripts/fresh_check.py $SC/shortlist.json

Lists each candidate in $SC/candidates.json (so already through the title triage and the German
drop) posted `reading.must_read_days` days ago or less that the shortlist neither sends nor
rejects. Exit 1 while any remain: read them, add each to `jobs` or `rejected`, and run it again.
write_pack.py prints any still unread at render time under "Fresh, not read yet", with the link,
so a run cut short still shows them.
"""
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cfg  # noqa: E402
from jobid import is_repeat  # noqa: E402


def _load(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _age(j, today):
    try:
        return (today - datetime.date.fromisoformat((j.get("date") or "")[:10])).days
    except ValueError:
        return None


def read_rows(sl):
    out = []
    for key in ("jobs", "rejected", "also_found", "borderline"):
        for r in sl.get(key) or []:
            if isinstance(r, dict) and (r.get("company") or r.get("title")):
                out.append(dict(company=r.get("company") or "", title=r.get("title") or "",
                                url=r.get("apply_url") or r.get("url") or ""))
    return out


def unread_fresh(sc, sl, days=None):
    """Candidates posted `days` days ago or less that the shortlist neither sends nor rejects,
    freshest first."""
    days = cfg.get("reading", "must_read_days") if days is None else days
    try:
        today = datetime.date.fromisoformat(sl.get("date") or "")
    except ValueError:
        today = datetime.date.today()
    read = read_rows(sl)
    out = []
    for c in _load(os.path.join(sc, "candidates.json"), []):
        a = _age(c, today)
        if a is None or a > days:
            continue
        if read and is_repeat(c.get("company") or "", c.get("title") or "", "", read, c.get("url") or ""):
            continue
        out.append(dict(c, age_days=a))
    return sorted(out, key=lambda c: (c["age_days"], -(c.get("prescore") or 0)))


if __name__ == "__main__":
    path = sys.argv[1]
    sl = _load(path, {})
    left = unread_fresh(os.path.dirname(os.path.abspath(path)), sl)
    for c in left:
        print("UNREAD FRESH  %s  %s | %s  %s" % ((c.get("date") or "")[:10], c.get("company"), c.get("title"),
                                                 c.get("url") or ""))
    print("%d fresh jobs in the field not read yet (posted %d days ago or less)"
          % (len(left), cfg.get("reading", "must_read_days")), file=sys.stderr)
    sys.exit(1 if left else 0)
