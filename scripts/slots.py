#!/usr/bin/env python3
"""Which run this is, from the UTC hour. One place for the rule.

Added 29 Sep 2026 with the noon run. Before it, "before 12:00 UTC is morning, after is evening"
was written out in five places (instructions/PROMPT.md, collect_all.py, health.py, build_latest.py,
rejected.py). A noon run at 11:30 UTC would have been named "morning" and overwritten the
morning's shortlist.

    morning   before 10:00 UTC   (the 10:00 Berlin run starts 08:00 UTC)
    noon      10:00 to 15:00 UTC (the 13:30 Berlin leftover run)
    evening   15:00 UTC or later (the 19:00 Berlin run starts 17:00 UTC)
"""
import datetime
import json
import os

ORDER = {"morning": 0, "noon": 1, "evening": 2}
NAMES = "morning|noon|evening"


def slot_for(utc_hour):
    return "morning" if utc_hour < 10 else "noon" if utc_hour < 15 else "evening"


def now_slot():
    return slot_for(datetime.datetime.now(datetime.timezone.utc).hour)


def elapsed_minutes(scratch, now=None):
    """Whole minutes since collect_all.py started this run, or None when unknown.

    30 Sep 2026: the morning run wrote "minutes": 72 by hand and said it was over time. Its log
    shows collection at 08:18 UTC and the push at 08:38 UTC. Believing it was late, it read 59 of
    318 candidates and skipped the employer apply links. The clock is now read, never written."""
    try:
        rec = json.load(open(os.path.join(scratch, "run_slot.json"), encoding="utf-8"))
        start = datetime.datetime.fromisoformat(rec["started"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return int((now - start).total_seconds() // 60)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "--elapsed":
        m = elapsed_minutes(sys.argv[2])
        print("unknown (no run_slot.json with a start time)" if m is None
              else "%d minutes since collection started" % m)
    else:
        print(now_slot())
