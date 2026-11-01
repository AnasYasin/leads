#!/usr/bin/env python3
"""When the funded-startup sweep is due, and a record of each sweep.

Added 29 Sep 2026. The sweep used to run on every morning run, about ten minutes each, and
over the 14 mornings from 15 to 28 Sep it produced one sent job (Omnisent, 27 Sep). The
search window is 90 days, so a daily sweep mostly found the same rounds again (Atira came
up on five mornings). the candidate chose weekly.

Due is decided from the date of the last completed sweep, not from the weekday, so a run
that fails or skips it does not push the sweep back a week: the next run of either slot
picks it up.

    python3 scripts/sweep_due.py                    DUE or NOT DUE, with the last sweep date
    python3 scripts/sweep_due.py --leads            funding posts since the last sweep, to start from
    python3 scripts/sweep_due.py --done N_FOUND "summary" [slug ...]
                                                    record a finished sweep (slugs added to instructions/COMPANIES.md)

Where the leads come from. The general web search returned listicles and aggregator pages
(Seedtable, Dealroom) on most mornings. deutsche-startups.de publishes a #DealMonitor post
per round ("Nomos erhält 20 Millionen") plus a daily #StartupTicker and a weekly
#Wochenrückblick, and its WordPress feed pages back 15 posts at a time with real dates.
Checked from the laptop on 29 Sep 2026: /feed/ answers 200 with posts dated that week, and
?paged=2..4 reach back to 7 Sep. eu-startups.com and sifted.eu answered 403 from the laptop.
"""
import datetime
import email.utils
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "state/sweep.json")
EVERY = 7


def load():
    return json.load(open(PATH, encoding="utf-8")) if os.path.exists(PATH) else {"last": "", "history": []}


FEED = "https://www.deutsche-startups.de/feed/"
FUNDING = re.compile(r"dealmonitor|startupticker|wochenr(ü|ue)ckblick|sammelt|millionen|investiert|"
                     r"finanzierung|seed|series [a-c]", re.I)


def leads(since, max_pages=8):
    """(date, title, link) for funding posts on or after `since`, newest first."""
    out, pg = [], 1
    while pg <= max_pages:
        url = FEED + ("?paged=%d" % pg if pg > 1 else "")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            xml = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        except Exception as ex:
            print("FEED ERROR page %d: %s" % (pg, str(ex)[:120]), file=sys.stderr)
            break
        items = re.findall(r"<item>(.*?)</item>", xml, re.S)
        if not items:
            break
        oldest = None
        for it in items:
            try:
                title = re.sub(r"<!\[CDATA\[|\]\]>", "", re.search(r"<title>(.*?)</title>", it, re.S).group(1)).strip()
                link = (re.search(r"<link>(.*?)</link>", it, re.S) or [None, ""])[1].strip()
                d = email.utils.parsedate_to_datetime(re.search(r"<pubDate>(.*?)</pubDate>", it).group(1)).date()
            except Exception:
                continue            # one malformed item must not lose the rest (review, 29 Sep 2026)
            oldest = d
            if d >= since and FUNDING.search(title):
                out.append((d.isoformat(), title.replace("&#8211;", "-").replace("\xa0", " "), link))
        if oldest and oldest < since:
            break
        pg += 1
    return out


def main(argv):
    st = load()
    today = datetime.date.today()
    if argv and argv[0] == "--leads":
        last = st.get("last") or ""
        since = datetime.date.fromisoformat(last) if last else today - datetime.timedelta(days=EVERY)
        since = min(since, today - datetime.timedelta(days=EVERY))
        rows = leads(since)
        for d, t, l in rows:
            print("%s | %s | %s" % (d, t[:150], l))
        print("%d funding posts since %s" % (len(rows), since), file=sys.stderr)
        if not rows:
            print("NO LEADS from the feed. Fall back to a web search and say so in the coverage table.", file=sys.stderr)
        return
    if argv and argv[0] == "--done":
        if len(argv) < 3 or not argv[1].isdigit():
            sys.exit("usage: sweep_due.py --done N_FOUND \"summary\" [slug ...]")
        st["last"] = today.isoformat()
        st["history"] = (st.get("history") or [])[-51:] + [
            dict(date=today.isoformat(), found=int(argv[1]), summary=argv[2][:400], added=argv[3:])]
        json.dump(st, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("sweep recorded for %s, next due %s" % (today, today + datetime.timedelta(days=EVERY)))
        return
    last = st.get("last") or ""
    if not last:
        print("DUE, no sweep on record")
        return
    days = (today - datetime.date.fromisoformat(last)).days
    if days >= EVERY:
        print("DUE, last sweep %s (%d day(s) ago)" % (last, days))
    else:
        print("NOT DUE, last sweep %s (%d day(s) ago), next due %s"
              % (last, days, datetime.date.fromisoformat(last) + datetime.timedelta(days=EVERY)))


if __name__ == "__main__":
    main(sys.argv[1:])
