#!/usr/bin/env python3
"""The store: one SQLite file built from the files the runs push. Added 1 Nov 2026.

    python3 scripts/store.py            rebuild store/jobs.db from the repository
    python3 scripts/store.py --check    also re-check every open job's link and stamp live or gone

The repository is the source: jobs/<id>.md (one pack per sent job, with the full description),
shortlists/<date>-<slot>.json, companies/*.json, state/applications.md, state/decisions.json and
state/rejected.json. store/jobs.db is derived from them and is not committed, so it can never
conflict; run this after every pull. Open it with sqlite3, DB Browser for SQLite or any editor
extension, or `import sqlite3` from a script.

Tables
    jobs          one row per sent job, every pack field plus the description, and applied_on,
                  applied_cv, outcome matched from applications.md (same company, same role)
    runs          one row per shortlist: date, slot, candidates, read_full, sent, minutes
    companies     the company cache, with how many jobs were sent per company
    applications  state/applications.md as columns
    decisions     every job a run read, with verdict, fit, gate and reason
    rejected      the hard kills remembered between runs
    checks        the link checks made with --check: state, reason, time
Views
    open_jobs     sent, not applied, not gone at the last check; freshest posting first, with
                  days_since_posted and days_since_sent
"""
import datetime
import glob
import json
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from jobid import same_company, same_role  # noqa: E402
import applications as apps_md  # noqa: E402

ROOT = os.path.dirname(HERE)
JOB_COLS = ["id", "company", "title", "location", "source", "fit", "priority", "band", "tier", "posted", "posted_listing",
            "date_note", "sent", "slot", "apply_url", "fallback_url", "linkedin_url", "xing_url", "ba_url", "employer_site",
            "people_url", "salary", "salary_ask", "staff", "size_class", "employment", "lang_line", "contact", "cv_base",
            "recruiter", "referral", "live_at_send", "prior_sent", "pack", "why", "gaps", "company_note", "description",
            "applied_on", "applied_cv", "outcome"]
VERDICT_LINES = {"Why it fits": "why", "Gaps": "gaps", "Company": "company_note"}

SCHEMA = """
CREATE TABLE jobs (%s, PRIMARY KEY (id));
CREATE TABLE runs (date TEXT, slot TEXT, candidates INTEGER, read_full INTEGER, sent INTEGER, minutes INTEGER, PRIMARY KEY (date, slot));
CREATE TABLE companies (name TEXT PRIMARY KEY, site TEXT, careers_url TEXT, what TEXT, staff TEXT, size_class TEXT, language TEXT,
                        last_seen TEXT, sent_count INTEGER);
CREATE TABLE applications (researched TEXT, company TEXT, role TEXT, location TEXT, verdict TEXT, docs_built TEXT, applied TEXT, outcome TEXT);
CREATE TABLE decisions (key TEXT, company TEXT, title TEXT, url TEXT, verdict TEXT, fit INTEGER, gate TEXT, reason TEXT, date TEXT, slot TEXT);
CREATE TABLE rejected (id TEXT, company TEXT, title TEXT, fit INTEGER, reason TEXT, first TEXT, last TEXT);
CREATE TABLE checks (id TEXT, state TEXT, why TEXT, checked_at TEXT);
CREATE VIEW open_jobs AS
  SELECT j.id, j.company, j.title, j.location, j.fit, j.priority, j.band, j.posted, j.sent, j.salary, j.salary_ask,
         j.apply_url, j.pack,
         CAST(julianday('now') - julianday(j.posted) AS INTEGER) AS days_since_posted,
         CAST(julianday('now') - julianday(j.sent) AS INTEGER) AS days_since_sent,
         (SELECT c.state FROM checks c WHERE c.id = j.id ORDER BY c.checked_at DESC LIMIT 1) AS last_check
  FROM jobs j
  WHERE j.applied_on IS NULL
    AND COALESCE((SELECT c.state FROM checks c WHERE c.id = j.id ORDER BY c.checked_at DESC LIMIT 1), '') <> 'GONE'
  ORDER BY j.posted DESC, j.sent DESC, j.priority DESC;
""" % ", ".join("%s %s" % (c, "INTEGER" if c in ("fit", "priority", "tier") else "TEXT") for c in JOB_COLS)


def _front_matter(head):
    fm = {}
    for l in head.split("\n")[1:]:
        k, _, v = l.partition(": ")
        if not k:
            continue
        try:
            fm[k] = json.loads(v) if v[:1] in "[{" or v in ("true", "false", "null") or re.fullmatch(r"-?\d+", v) else v
        except Exception:
            fm[k] = v
    return fm


def read_pack(path):
    """The front matter plus why, gaps, company_note and the full description of one pack."""
    txt = open(path, encoding="utf-8").read()
    head, _, body = txt.partition("\n---\n")
    j = _front_matter(head)
    j["pack"] = "jobs/" + os.path.basename(path)
    for line in body.split("\n"):
        for label, key in VERDICT_LINES.items():
            if line.startswith(label + ":"):
                j[key] = line[len(label) + 1:].strip()
    m = re.search(r"^## Full job description[^\n]*\n", body, re.M)
    j["description"] = body[m.end():].strip() if m else ""
    return j


def _applied_match(j, rows):
    """(applied_on, cv, outcome) from the applications.md rows for this job, or Nones."""
    for r in rows:
        if r["Applied"].lower().startswith("yes") and same_company(r["Company"], j.get("company") or "") \
           and same_role(r["Role"], j.get("title") or "", r["Company"], loose=True):
            return r["Applied"], r["Docs built"], r["Outcome"]
    return None, None, None


def _val(v):
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return int(v)
    return v


def build(root=ROOT, out=None, check=False):
    out = out or os.path.join(root, "store", "jobs.db")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".building"
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    apps = apps_md.rows(os.path.join(root, "state", "applications.md"))
    db.executemany("INSERT INTO applications VALUES (?,?,?,?,?,?,?,?)", [tuple(r[c] for c in apps_md.COLS) for r in apps])
    n_jobs = 0
    for f in sorted(glob.glob(os.path.join(root, "jobs", "*.md"))):
        j = read_pack(f)
        j["applied_on"], j["applied_cv"], j["outcome"] = _applied_match(j, apps)
        db.execute("INSERT OR REPLACE INTO jobs (%s) VALUES (%s)" % (", ".join(JOB_COLS), ", ".join("?" * len(JOB_COLS))),
                   [_val(j.get(c)) for c in JOB_COLS])
        n_jobs += 1
    for f in sorted(glob.glob(os.path.join(root, "shortlists", "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict) or not d.get("date"):
            continue
        db.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?)",
                   (d.get("date"), d.get("slot"), _int(d.get("candidates")), _int(d.get("read_full")),
                    len(d.get("jobs") or []), _int(d.get("minutes"))))
    for f in sorted(glob.glob(os.path.join(root, "companies", "*.json"))):
        try:
            c = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(c, dict) or not c.get("name"):
            continue
        db.execute("INSERT OR REPLACE INTO companies VALUES (?,?,?,?,?,?,?,?,?)",
                   (c.get("name"), c.get("site"), c.get("careers_url"), c.get("what"), _val(c.get("staff")), c.get("size_class"),
                    c.get("language"), c.get("last_seen"), len(c.get("sent") or [])))
    for d in _jl(os.path.join(root, "state", "decisions.json")):
        db.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (d.get("key"), d.get("company"), d.get("title"), d.get("url"), d.get("verdict"), _int(d.get("fit")),
                    d.get("gate"), d.get("reason"), d.get("date"), d.get("slot")))
    for r in _jl(os.path.join(root, "state", "rejected.json")):
        db.execute("INSERT INTO rejected VALUES (?,?,?,?,?,?,?)",
                   (r.get("id"), r.get("company"), r.get("title"), _int(r.get("fit")), r.get("reason"), r.get("first"), r.get("last")))
    if os.path.exists(out):
        # keep earlier link checks
        try:
            old = sqlite3.connect(out)
            rows = old.execute("SELECT id, state, why, checked_at FROM checks").fetchall()
            old.close()
            db.executemany("INSERT INTO checks VALUES (?,?,?,?)", rows)
        except sqlite3.Error:
            pass
    if check:
        import check_live
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
        for jid, url in db.execute("SELECT id, apply_url FROM open_jobs WHERE apply_url <> ''").fetchall():
            st = check_live.check(url)
            state, why = (st[0], st[1]) if isinstance(st, (tuple, list)) and len(st) >= 2 else (str(st), "")
            db.execute("INSERT INTO checks VALUES (?,?,?,?)", (jid, str(state), str(why)[:200], now))
    db.commit()
    db.close()
    os.replace(tmp, out)
    return out, n_jobs


def _jl(path):
    try:
        v = json.load(open(path, encoding="utf-8"))
        return v if isinstance(v, list) else []
    except (OSError, ValueError):
        return []


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    path, n = build(check="--check" in sys.argv)
    db = sqlite3.connect(path)
    open_n = db.execute("SELECT COUNT(*) FROM open_jobs").fetchone()[0]
    print("%s: %d jobs, %d open (sent, not applied, not gone)" % (os.path.relpath(path, ROOT), n, open_n))
