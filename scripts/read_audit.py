#!/usr/bin/env python3
"""How a run read its jobs, from the record write_pack.py stores with the shortlist.

Added 3 Oct 2026. Between 30 Sep and 2 Oct every run reported "read in full" after printing 300 to
2,800 characters of each job, and nothing checked the claim. Since 2 Oct the reader counts what it
printed, and write_pack.py stores one entry per batch in the shortlist as `reading`: when the batch
was printed, how many jobs and characters it held, and when its verdicts came back. This script
prints that record, so a run can be checked after its scratch directory is gone.

    python3 scripts/read_audit.py                      the newest shortlist
    python3 scripts/read_audit.py shortlists/2026-10-03-morning.json

It sets no pass mark for speed. No real run has been measured yet, so the first runs give the
normal range. It does report what is wrong whatever the speed: a full run with no record, a batch
without all its verdicts, and a read count that does not match the batches.
"""
import datetime
import glob
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDER = {"morning": 0, "noon": 1, "evening": 2}


def newest(root=ROOT):
    fs = glob.glob(os.path.join(root, "shortlists", "*.json"))
    def key(f):
        b = os.path.basename(f)[:-5]
        return b[:10], ORDER.get(b[11:], 9)
    return max(fs, key=key) if fs else None


def _t(s):
    try:
        return datetime.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def audit(sl):
    """(rows, problems, summary) for one shortlist dict."""
    rec = sl.get("reading")
    problems, rows = [], []
    if rec is None:
        if sl.get("candidates"):
            problems.append("no reading record: this run was rendered without the reader's log")
        return rows, problems, {}
    for b in rec:
        a, v = _t(b.get("printed_at")), _t(b.get("verdicts_at"))
        secs = int((v - a).total_seconds()) if a and v else None
        rows.append(dict(n=b.get("n"), jobs=b.get("jobs", 0), chars=b.get("chars", 0), verdicts=b.get("verdicts", 0), seconds=secs))
        if b.get("verdicts", 0) < b.get("jobs", 0):
            problems.append("batch %s: %d of %d jobs have a verdict" % (b.get("n"), b.get("verdicts", 0), b.get("jobs", 0)))
        if secs is not None and secs < 0:
            problems.append("batch %s: the verdicts are dated before the batch was printed" % b.get("n"))
    done = sum(r["verdicts"] for r in rows)
    if sl.get("read_full") is not None and done != sl.get("read_full"):
        problems.append("read_full says %s, the batches hold %d verdicts" % (sl.get("read_full"), done))
    # The shortlist file never stores the job text; it is in each job's pack (jobs/<id>.md). An empty
    # text at send time is refused by final_check.py and write_pack.py, so it is not checked here.
    timed = [r for r in rows if r["seconds"] is not None and r["seconds"] > 0]
    summ = dict(batches=len(rows), jobs=sum(r["jobs"] for r in rows), chars=sum(r["chars"] for r in rows))
    if timed:
        summ["median_seconds"] = int(statistics.median(r["seconds"] for r in timed))
        summ["fastest_seconds"] = min(r["seconds"] for r in timed)
        summ["chars_per_second"] = int(sum(r["chars"] for r in timed) / max(1, sum(r["seconds"] for r in timed)))
    return rows, problems, summ


def main(argv):
    path = argv[1] if len(argv) > 1 else newest()
    if not path:
        print("no shortlist found")
        return 1
    sl = json.load(open(path, encoding="utf-8"))
    rows, problems, summ = audit(sl)
    print("%s: candidates %s, read in full %s, left unread %s, run time %s minutes"
          % (os.path.basename(path), sl.get("candidates"), sl.get("read_full"), sl.get("left_unread"), sl.get("minutes")))
    if rows:
        print("batch  jobs   chars  verdicts  seconds from print to verdicts")
        for r in rows:
            print("%5s %5d %7d %9d  %s" % (r["n"], r["jobs"], r["chars"], r["verdicts"], "-" if r["seconds"] is None else r["seconds"]))
        print("total: %(batches)d batches, %(jobs)d jobs, %(chars)d characters printed" % summ)
        if "median_seconds" in summ:
            print("per batch: median %(median_seconds)d s, fastest %(fastest_seconds)d s, %(chars_per_second)d characters per second overall" % summ)
    for p in problems:
        print("PROBLEM  " + p)
    print("%d problems" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
