#!/usr/bin/env python3
"""Run every collector in parallel into one scratch directory, then the filter.

This replaces the hand-typed sequence of collector calls the cloud run used to re-derive
every time. One command, one directory, one candidates.json at the end.

    python3 scripts/collect_all.py <scratchdir> [--skip getro,berlin] [--hours 24]

Sources and the files they write:
    ba.json         Bundesagentur API (collect_ba.py)
    ats.json        company ATS boards from collect_ats.py
    getro.json      VC portfolio boards (collect_getro.py)  - morning run only, see instructions/PROMPT.md
    talent.json     de.talent.com cards (collect_talent.py)
    arbeitnow.json  arbeitnow feed (collect_arbeitnow.py)
    linkedin.json   LinkedIn guest endpoint, last N hours (collect_linkedin.py)
    xing.json       XING search plus detail pages (collect_xing.py)
    stepstone.json  StepStone listing plus job pages, last 3 days (collect_stepstone.py), cloud only

Each collector's stderr is saved as <name>.log in the scratch directory, and a one-line
summary per source is printed at the end so the coverage table can be filled in from it.
"""
import os, subprocess, sys, time, datetime, json
import concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
scratch = sys.argv[1]
os.makedirs(scratch, exist_ok=True)
skip = set()
hours = "24"
args = sys.argv[2:]
for i, a in enumerate(args):
    if a == "--skip":
        skip = set(args[i + 1].split(","))
    if a == "--hours":
        hours = args[i + 1]

# Getro is 180,000 rows for about one hit a week. Morning slot only (any run before 10:00 UTC,
# see scripts/slots.py), unless --force-getro is passed.
utc_now = datetime.datetime.now(datetime.timezone.utc)
utc_hour = utc_now.hour
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from slots import slot_for
SLOT = slot_for(utc_hour)
# 29 Sep 2026: the run's date and slot as of collection. write_pack.py refuses a shortlist that
# names another, so a run cannot overwrite an earlier run's shortlist under the wrong name.
# 30 Sep 2026: "started" lets write_pack.py and `slots.py --elapsed` read the run time off the clock.
json.dump({"date": utc_now.date().isoformat(), "slot": SLOT, "started": utc_now.isoformat()}, open(os.path.join(scratch, "run_slot.json"), "w"))
if "getro" not in skip and SLOT != "morning" and "--force-getro" not in args:
    skip.add("getro")

# 29 Sep 2026: the noon run collects nothing. It reads the jobs the morning and evening runs left
# unread (scripts/leftover.py), so new postings cannot push those leftovers down the list again.
# New postings wait for the evening run. --collect forces a normal collection at noon.
if SLOT == "noon" and "--collect" not in args:
    import leftover
    n, sent, applied = leftover.load_for_noon(scratch)
    print("noon run: no collection. candidates.json holds %d leftover jobs from state/leftover.json "
          "(%d sent since and %d applied to since were dropped)" % (n, sent, applied), file=sys.stderr)
    sys.exit(0)

JOBS = {
    "ba": ["collect_ba.py", "ba.json"],
    "ats": ["collect_ats.py", "ats.json"],
    "getro": ["collect_getro.py", "getro.json"],
    "talent": ["collect_talent.py", "talent.json"],
    "arbeitnow": ["collect_arbeitnow.py", "arbeitnow.json"],
    "linkedin": ["collect_linkedin.py", "linkedin.json", hours],
    "xing": ["collect_xing.py", "xing.json"],
    # cloud only: the laptop gets 403 from StepStone. Verified in the cloud 8 Sep 2026.
    "stepstone": ["collect_stepstone.py", "stepstone.json", "3"],
}


def run(name):
    script, out, *extra = JOBS[name]
    t0 = time.time()
    cmd = [sys.executable, os.path.join(HERE, script), os.path.join(scratch, out)] + extra
    with open(os.path.join(scratch, name + ".log"), "w") as log:
        # A timeout must not stop the filter, health and prune steps below (review, 29 Sep 2026).
        try:
            p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=log, timeout=1500)
        except subprocess.TimeoutExpired:
            log.write("\nTIMEOUT after 1500 s, collector killed\n")
            p = subprocess.CompletedProcess(cmd, -9)
    last = ""
    try:
        last = open(os.path.join(scratch, name + ".log")).read().strip().splitlines()[-1]
    except Exception:
        pass
    return name, p.returncode, time.time() - t0, last[:110]


names = [n for n in JOBS if n not in skip]
print("collecting: %s  (skipped: %s)" % (", ".join(names), ", ".join(sorted(skip)) or "none"),
      file=sys.stderr)
with cf.ThreadPoolExecutor(max_workers=max(1, len(names))) as ex:
    for name, rc, dt, last in ex.map(run, names):
        print("%-10s rc=%d %5.0fs  %s" % (name, rc, dt, last), file=sys.stderr)

for n in skip:
    if n not in JOBS:
        continue            # e.g. the old "berlin" source; its name in --skip must not crash the run
    p = os.path.join(scratch, JOBS[n][1])
    if not os.path.exists(p):
        open(p, "w").write("[]")

print("--- filter_run.py ---", file=sys.stderr)
subprocess.run([sys.executable, os.path.join(HERE, "filter_run.py"), scratch], check=False)

# 29 Sep 2026: the funded-startup sweep is weekly. Say here, in the output every run reads,
# whether it is due, and fetch its leads, so it cannot be missed by skipping a PROMPT step.
print("--- funded-startup sweep ---", file=sys.stderr)
due = subprocess.run([sys.executable, os.path.join(HERE, "sweep_due.py")], capture_output=True, text=True)
print((due.stdout or due.stderr).strip(), file=sys.stderr)
if due.stdout.startswith("DUE"):
    try:
        with open(os.path.join(scratch, "sweep_leads.txt"), "w") as fh:
            r = subprocess.run([sys.executable, os.path.join(HERE, "sweep_due.py"), "--leads"],
                               stdout=fh, stderr=subprocess.PIPE, text=True, timeout=300)
        print("SWEEP DUE THIS RUN. Leads in sweep_leads.txt. %s" % r.stderr.strip()[-300:], file=sys.stderr)
    except Exception as ex:
        # A slow or broken feed must not stop the health check below or fail the collection.
        print("SWEEP DUE THIS RUN. The leads feed failed (%s); use a web search." % str(ex)[:80], file=sys.stderr)

# 29 Sep 2026: source and board health across runs (scripts/health.py). Recorded into
# state/health.json every run; set RADAR_HEALTH_DRY=1 for a laptop test so nothing is written.
print("--- health ---", file=sys.stderr)
hcmd = [sys.executable, os.path.join(HERE, "health.py"), scratch, "--skipped", ",".join(sorted(skip)) or "-"]
# Dry by default on the laptop (review, 29 Sep 2026): a laptop test would otherwise add laptop
# rows to the history (no StepStone, no Greenhouse DNS) and dirty a tracked file under pick.py.
# The laptop is recognised by ~/job_hunt/applications.md, which the cloud does not have.
# RADAR_HEALTH_DRY=1 forces dry, RADAR_HEALTH_RECORD=1 forces recording.
on_laptop = os.path.exists(os.path.expanduser("~/job_hunt/applications.md"))
if os.environ.get("RADAR_HEALTH_DRY") or (on_laptop and not os.environ.get("RADAR_HEALTH_RECORD")):
    hcmd.append("--dry")
try:
    h = subprocess.run(hcmd, capture_output=True, text=True, timeout=120)
except Exception as ex:
    h = subprocess.CompletedProcess(hcmd, 1, "", "health failed: %s" % str(ex)[:80])
print((h.stdout + h.stderr).strip() or "health: no output", file=sys.stderr)

# 29 Sep 2026: delete packs for jobs he never applied to once they are really gone
# (scripts/prune_packs.py). Evening run only, dry on the laptop like the health check.
if SLOT == "evening" or "--force-prune" in args:
    print("--- prune old packs ---", file=sys.stderr)
    pcmd = [sys.executable, os.path.join(HERE, "prune_packs.py"), scratch]
    if os.environ.get("RADAR_HEALTH_DRY") or (on_laptop and not os.environ.get("RADAR_HEALTH_RECORD")):
        pcmd.append("--dry")
    try:
        pr = subprocess.run(pcmd, capture_output=True, text=True, timeout=900)
        print((pr.stdout + pr.stderr).strip()[-3000:] or "prune: no output", file=sys.stderr)
    except Exception as ex:
        print("prune failed, nothing deleted: %s" % str(ex)[:80], file=sys.stderr)

# 2 Oct 2026 (docs/PROBLEMS.md 7.3): on 30 Sep the morning run waited five minutes for candidates.json in
# the repo root. It is in the scratch directory, and it exists as soon as this script returns.
print("--- done ---", file=sys.stderr)
print("candidates.json is at %s (not in the repo). Collection is finished; do not wait for anything else."
      % os.path.join(os.path.abspath(scratch), "candidates.json"), file=sys.stderr)
