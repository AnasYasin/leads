#!/usr/bin/env python3
"""Memory of jobs a run read and dropped, so the next runs do not read them again.

Added 29 Sep 2026. `state/seen.json` only holds jobs that were sent, so a rejected job came back
as fresh on every run and was read in full again. Exxeta's Physical AI role was read and
dropped on the German line 13 times between 22 and 28 Sep.

ONLY HARD KILLS ARE REMEMBERED: a quoted German requirement above B1, or a nationality or
security-clearance rule. Those are facts in the posting text and a second read finds the
same sentence. Judgement rejections are NOT remembered, on purpose. A backtest over the 26
runs from 15 to 28 Sep found that remembering every rejection would have hidden 25 jobs a
later run sent, and the candidate applied to about 10 of them (several companies,
amber, Jobgether, adjoe...). Runs disagree on judgement calls within a day or two, and the
later call is often the one he acts on. With hard kills only, the same backtest skips 456
of 1,195 rejections (38%) and hides 8 sent jobs, every one of them a job an earlier run had
quoted a C1 or NATO line for. the candidate chose to hide those (29 Sep 2026).

`state/rejected.json` at the repo root holds one entry per dropped job:
    {"id", "company", "title", "fit", "reason", "first", "last"}
`write_pack.py` merges each run's `rejected` list into it. `filter_run.py` skips a
candidate that matches an entry whose `last` date is within DAYS, using the same
`is_repeat` as the seen check. After DAYS the job is read once more, and if it is dropped
again `last` moves forward.

    python3 scripts/rejected.py --seed [days]   rebuild from the Rejected sections of shortlists/
    python3 scripts/rejected.py --stats         counts
"""
import datetime, glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jobid import is_repeat, canonical_id

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "state/rejected.json")
DAYS = 14      # how long a rejection suppresses a re-read
KEEP = 45      # entries older than this are pruned from the file

# Rejections that must not suppress anything. An "already sent" line is a repeat that
# slipped the seen check and was caught by hand; state/seen.json already covers it, and storing
# it here would only hide the fact that the seen check leaked.
NOT_A_VERDICT = re.compile(r"already sent|already in seen|sent before|repeat of", re.I)


GERMAN_KILL = re.compile(
    r"drop band|language drop|disqualified on (german|language)|german in the drop"
    r"|(fluent|native|excellent|business[- ]fluent|very good|strong|sehr gute?\w*|verhandlungssicher\w*"
    r"|flie(ß|ss)end\w*|exzellente?\w*)\W{1,3}(german|deutsch)"
    r"|(german|deutsch)\w*\W{0,3}(min\.?|mindestens|mind\.)?\W{0,3}\(?(C1|C2)\b"
    r"|\bC1\b[^.]{0,40}(required|voraus|erforderlich|deutsch)", re.I)
CLEARANCE_KILL = re.compile(
    r"(nato|nationality|citizenship|security clearance|sicherheitsüberprüfung)[^.]{0,80}"
    r"(required|require|must|disqualif|voraus)"
    r"|(disqualif|required)[^.]{0,40}(nato|nationality|citizenship|clearance|sicherheitsüberprüfung)", re.I)
# Reasons that mention German only to say it was fine. Checked against all 1,818 rejection
# reasons in shortlists/ on 29 Sep 2026; without this, "B2 German would have been
# acceptable" and "German a plus reads fine" counted as kills.
NOT_KILL = re.compile(r"german (is )?(only )?(a )?plus|would have been (fine|acceptable)|language (was|is) fine"
                      r"|is fine at b|german a plus|lang_band script flagged"
                      # negated requirements (review, 29 Sep 2026)
                      r"|(german|deutsch|clearance|citizenship|nationality)\w*[^.]{0,20}(not required|not needed|not a must|nicht erforderlich)"
                      r"|\bno (security )?clearance (is )?required"
                      # "Deutsch- oder Englischkenntnisse" is German OR English (Koara, review 29 Sep 2026)
                      r"|deutsch\w*[- ]+oder englisch|german or english|englisch\w* oder deutsch|english or german", re.I)


def hard(reason):
    """True when the reason quotes a German-above-B1 or nationality/clearance requirement."""
    reason = reason or ""
    if NOT_KILL.search(reason):
        return False
    return bool(GERMAN_KILL.search(reason) or CLEARANCE_KILL.search(reason))


def load():
    return json.load(open(PATH, encoding="utf-8")) if os.path.exists(PATH) else []


def save(rows):
    json.dump(rows, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def active(rows, today, days=DAYS):
    cut = (datetime.date.fromisoformat(today) - datetime.timedelta(days=days)).isoformat()
    return [r for r in rows if (r.get("last") or "") >= cut]


def merge(rows, rejected, date):
    """Fold one run's `rejected` list into rows. Returns the number added."""
    added = 0
    for r in rejected or []:
        co, ti = (r.get("company") or "").strip(), (r.get("title") or "").strip()
        if not co or not ti or NOT_A_VERDICT.search(r.get("reason") or "") or not hard(r.get("reason")):
            continue
        m = is_repeat(co, ti, "", rows)
        if m:
            m["last"] = max(m.get("last") or "", date)
            m["fit"], m["reason"] = r.get("fit", m.get("fit")), (r.get("reason") or m.get("reason", ""))[:300]
            m["gate"] = r.get("gate") or m.get("gate", "")
            continue
        # 2 Oct 2026: the gate is stored, so a rejection can be checked without the run log (docs/PROBLEMS.md 6.5).
        rows.append(dict(id=canonical_id(co, ti), company=co, title=ti, fit=r.get("fit"), gate=r.get("gate") or "",
                         reason=(r.get("reason") or "")[:300], first=date, last=date))
        added += 1
    cut = (datetime.date.fromisoformat(date) - datetime.timedelta(days=KEEP)).isoformat()
    rows[:] = [x for x in rows if (x.get("last") or "") >= cut]
    return added


def split(cands, rows, today, days=DAYS):
    """Partition candidates into (kept, skipped). skipped is a list of (candidate, entry)."""
    act = active(rows, today, days)
    kept, skipped = [], []
    for j in cands:
        m = is_repeat(j.get("company") or "", j.get("title") or "", "", act) if act else None
        (skipped.append((j, m)) if m else kept.append(j))
    return kept, skipped


LINE = re.compile(r"^- (?P<title>.+?) — (?P<company>.+?) · fit (?P<fit>[^ ·]+) · (?:gate (?P<gate>[a-z_]+) · )?(?P<reason>.*)$")


def parse_md(path):
    t = open(path, encoding="utf-8").read()
    if "## Rejected" not in t:
        return []
    out = []
    for l in t.split("## Rejected", 1)[1].split("\n"):
        m = LINE.match(l.strip())
        if m:
            d = m.groupdict()
            d["fit"] = int(d["fit"]) if d["fit"].isdigit() else None
            out.append(d)
    return out


def seed(days=DAYS, today=None):
    today = today or datetime.date.today().isoformat()
    cut = (datetime.date.fromisoformat(today) - datetime.timedelta(days=days)).isoformat()
    rows = []
    for f in sorted(glob.glob(os.path.join(ROOT, "shortlists", "*-*.md"))):
        m = re.search(r"(\d{4}-\d{2}-\d{2})-(morning|noon|evening)\.md$", f)
        if m and m.group(1) >= cut:
            merge(rows, parse_md(f), m.group(1))
    return rows


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--seed":
        rows = seed(int(sys.argv[2]) if len(sys.argv) > 2 else DAYS)
        save(rows)
        print("state/rejected.json seeded, %d entries" % len(rows))
    else:
        rows = load()
        today = datetime.date.today().isoformat()
        print("%d entries, %d active (last %d days)" % (len(rows), len(active(rows, today)), DAYS))
