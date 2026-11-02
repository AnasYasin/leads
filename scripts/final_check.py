#!/usr/bin/env python3
"""The repeat check on the final list, run once before write_pack.py. Use this, not is_repeat by hand.

Added 29 Sep 2026. That morning the run called is_repeat by hand on its final list. is_repeat
matched Preply and Quantum-Systems to jobs sent in August, the run dropped both and rendered seven
jobs, then noticed filter_run.py had tagged them as second openings (both requisitions open at
once), put them back and rendered nine. Two emails went out. This script applies the same rule as
the filter (jobid.second_opening), with the description, so a repeat and a second opening can no
longer be confused.

    python3 scripts/final_check.py $SC/shortlist.json

For each job it prints one line:
    OK              not sent before
    SECOND OPENING  matches a sent job, but both are open now and the titles differ: keep, and say
                    in `why` what differs from the sent one
    REPEAT          the same job was sent before: drop it
    APPLIED         he already applied to this role: drop it
    GERMAN          the description states a German level he does not have, in one clear sentence: drop it
    GERMAN?         the description has an unclear German line: read it, then either move the job to
                    `rejected` (gate german) or keep it with that sentence quoted in `lang_line`
    CLEARANCE       the description requires a nationality or a security clearance: drop it
    UNREAD          scripts/read_next.py did not print this job in full, or it has no "send" verdict: read
                    it and hand in a verdict, or take it out of `jobs`
Exit code 1 when any job is REPEAT or APPLIED, so the list is fixed before rendering.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from jobid import norm_url, same_company, same_role, sent_match  # noqa: E402
from lang_band import german  # noqa: E402
import clearance  # noqa: E402
from applications import applied  # noqa: E402

ROOT = os.path.dirname(HERE)
BAD = ("REPEAT", "APPLIED", "GERMAN", "GERMAN?", "CLEARANCE", "UNREAD")
POOL_FILES = ["ats", "ba", "linkedin", "xing", "stepstone", "talent", "arbeitnow", "getro"]


def _load(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def pool_urls(scratch):
    # 29 Sep 2026: the noon run collects nothing. scripts/leftover.py writes pool_urls.json with the
    # sent jobs' links that were live when the morning or evening run collected the row.
    urls = {norm_url(u) for u in _load(os.path.join(scratch, "pool_urls.json"), []) if isinstance(u, str)}
    for f in POOL_FILES:
        rows = _load(os.path.join(scratch, f + ".json"), [])
        for r in rows if isinstance(rows, list) else []:
            if isinstance(r, dict) and r.get("url"):
                urls.add(norm_url(r["url"]))
    return urls


def _norm(t):
    return re.sub(r"[^0-9a-zà-ÿ]+", "", (t or "").lower())


def quoted(lang_line, lines):
    """True when `lang_line` quotes one of the posting's unclear German sentences: 30 letters of it
    in a row are enough, so a shortened quote still counts."""
    have = _norm(lang_line)
    for l in lines:
        n = _norm(l)
        if n and (n in have or any(n[i:i + 30] in have for i in range(0, max(1, len(n) - 29), 3))):
            return True
    return False


def check(shortlist_path, root=ROOT):
    scratch = os.path.dirname(os.path.abspath(shortlist_path))
    sl = _load(shortlist_path, {})
    seen = _load(os.path.join(root, "state/seen.json"), [])
    date = sl.get("date") if isinstance(sl, dict) else None
    # A re-render of this same run must not match its own first render. Only this run's own sends
    # are ignored: before 29 Sep 2026 every send of the same date was, so a noon or evening run
    # could send again a job the morning had sent. Entries written before `slot` was recorded
    # count as another run's sends.
    slot = sl.get("slot") if isinstance(sl, dict) else None
    seen = [e for e in seen if not (date and (e.get("sent") or "") == date and e.get("slot") == slot)]
    urls = pool_urls(scratch)
    apps = applied(os.path.join(root, "state/applications.md"))
    import decisions
    prints = decisions.sent_prints(root, date if isinstance(date, str) and len(date) == 10 else None)
    prints = [(e, fp) for e, fp in prints if not ((e.get("sent") or "") == date and e.get("slot") == slot)]  # this run's own first render
    out = []
    # 2 Oct 2026: a job is sent only when scripts/read_next.py printed all of it and it has a "send"
    # verdict. On 2 Oct three jobs went out with an empty description, one of them a NATO-nationality role.
    import verdict as V
    jobs = [j for j in ((sl.get("jobs") or []) if isinstance(sl, dict) else []) if isinstance(j, dict)]
    unread = {id(j): why for j, why in V.unread_jobs(scratch, jobs)}
    for j in jobs:
        co, ti = j.get("company") or "", j.get("title") or ""
        if id(j) in unread:
            out.append(("UNREAD", co, ti, unread[id(j)]))
            continue
        link = j.get("apply_url") or j.get("fallback_url") or ""
        if any(same_company(c, co) and same_role(t, ti, c) for c, t in apps):
            out.append(("APPLIED", co, ti, "already in state/applications.md"))
            continue
        # 30 Sep 2026: the facts a rejection rests on are checked on every job about to be sent too.
        # Over 128 runs, 16 jobs rejected on a quoted C1 or fluent-German line were sent by a later run
        # that missed the line. the referral company referral jobs are exempt (instructions/PROFILE.md).
        if not j.get("referral"):
            verdict, lines = german(j.get("desc") or "")
            if verdict == "drop":
                out.append(("GERMAN", co, ti, lines[0][:150]))
                continue
            # 2 Oct 2026: an unclear German line may be sent, but only with the sentence shown, so
            # the candidate can judge it. The agent quotes it in `lang_line` and sets the band.
            if verdict == "decide" and not quoted(j.get("lang_line"), lines):
                out.append(("GERMAN?", co, ti, "quote this in lang_line and decide: " + lines[0][:150]))
                continue
            cv, clines = clearance.check(j.get("desc") or "")
            if cv == "drop":
                out.append(("CLEARANCE", co, ti, clines[0][:200]))
                continue
        m, so = sent_match(co, ti, j.get("location", ""), link, j.get("desc") or "", seen, urls, prints,
                           links=[j.get("fallback_url") or "", j.get("url") or ""])
        if not m:
            out.append(("OK", co, ti, ""))
        elif so:
            out.append(("SECOND OPENING", co, ti, "beside %s | %s (sent %s)" % (m.get("company"), m.get("title"), m.get("sent"))))
        else:
            out.append(("REPEAT", co, ti, "of %s | %s (sent %s)" % (m.get("company"), m.get("title"), m.get("sent"))))
    return out


if __name__ == "__main__":
    rows = check(sys.argv[1])
    for verdict, co, ti, note in rows:
        print("%-15s %s | %s%s" % (verdict, co[:40], ti[:70], ("  " + note) if note else ""))
    bad = sum(1 for r in rows if r[0] in BAD)
    print("%d jobs checked: %d to drop, %d second openings" % (
        len(rows), bad, sum(1 for r in rows if r[0] == "SECOND OPENING")), file=sys.stderr)
    sys.exit(1 if bad else 0)
