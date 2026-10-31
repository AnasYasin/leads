#!/usr/bin/env python3
"""Re-date packs from the employer board. Run once after a change to board_date.py, or for a
day whose email carried aggregator dates.

    fix_dates.py [YYYY-MM-DD]      packs sent that day (default today); prints a table, rewrites
                                   `posted`, keeps the old value in `posted_listing`, adds `date_note`.
"""
import datetime, os, re, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_date import true_date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
day = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
seen = json.load(open(os.path.join(ROOT, "state/seen.json")))


def fm_of(path):
    fm, lines = {}, open(path, encoding="utf-8").read().split("\n")
    for l in lines[1:]:
        if l == "---":
            break
        k, _, v = l.partition(": ")
        fm[k] = v
    return fm


def set_fm(path, key, value):
    txt = open(path, encoding="utf-8").read()
    head, sep, rest = txt.partition("\n---\n")
    if re.search(r"^%s: " % re.escape(key), head, re.M):
        head = re.sub(r"^%s: .*$" % re.escape(key), "%s: %s" % (key, value), head, flags=re.M)
    else:
        head += "\n%s: %s" % (key, value)
    open(path, "w", encoding="utf-8").write(head + sep + rest)


print("%-10s %-10s %-44s %-24s %s" % ("pack", "board", "title", "company", "note"))
for e in seen:
    if e.get("sent") != day or not e.get("pack"):
        continue
    path = os.path.join(ROOT, e["pack"])
    fm = fm_of(path)
    found, note = "", "no employer url"
    for u in (fm.get("apply_url"), fm.get("fallback_url")):
        if not u or "linkedin.com" in u or "xing.com" in u:
            continue
        found, note = true_date(u, fm.get("title", ""))
        if found:
            break
    old = fm.get("posted") or "-"
    print("%-10s %-10s %-44s %-24s %s" % (old, found or "-", fm.get("title", "")[:44], fm.get("company", "")[:24], note[:50]))
    if found and found != old[:10]:
        if not fm.get("posted_listing"):
            set_fm(path, "posted_listing", old if old != "-" else "")
        set_fm(path, "posted", found)
        set_fm(path, "date_note", "%s; the listing said %s" % (note, old))
