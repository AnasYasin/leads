#!/usr/bin/env python3
"""Render the run from one structured file. The agent writes `shortlist.json` in the
scratch directory; this script turns it into everything that leaves the run:

    shortlists/<date>-<slot>.md    the email, two sections by German band, fixed layout
    jobs/<id>.md                   one pack per sent job, full description and direct links,
                                   what pick.py hands to the local job_hunt session
    state/seen.json                      appended, with a `pack` path per job, pruned to 90 days

Why: the email layout drifted from run to run when it was hand-written, the language line
was sometimes missing, and the full description the agent had already fetched was thrown
away, so the local session had to scrape it all again. Now the agent writes facts and
prose into JSON and the layout is code.

It also runs check_live.py on every apply url and refuses to render a job that is GONE,
so a vanished job is caught at the last moment.

Usage: write_pack.py <scratchdir>/shortlist.json
Schema: see SHORTLIST_SCHEMA below. Missing optional fields render as empty.
"""
import datetime, json, os, re, subprocess, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from jobid import canonical_id, is_repeat, same_company, company_tokens
from board_date import true_date
import company_cache
import cfg
import salary
from slots import elapsed_minutes


def board_of(url):
    """kind:slug for an ATS url, else ''."""
    try:
        import deepdive
        k, sl = deepdive.detect(url or "")
        return "%s:%s" % (k, sl) if k else ""
    except Exception:
        return ""


def freshness(iso, today):
    """instructions/PROFILE.md freshness bonus."""
    if not iso or not re.match(r"\d{4}-\d{2}-\d{2}", iso):
        return -2
    d = (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(iso[:10])).days
    return 2 if d < 1 else 1 if d <= 3 else 0 if d <= 14 else -1 if d <= 30 else -2

# The gates a rejection must name (instructions/PROFILE.md, "When to reject", 30 Sep 2026).
GATES = {"german", "clearance", "years", "phd", "non_software", "lead", "field", "closed", "repeat", "unpaid", "no_text"}

SHORTLIST_SCHEMA = {
    "date": "YYYY-MM-DD", "slot": "morning|evening",
    "intro": "one or two plain sentences on the run",
    "jobs": [{
        "company": "", "title": "", "location": "", "employment": "full-time|...",
        "posted": "YYYY-MM-DD or ''", "source": "Bundesagentur|ATS/ashby|linkedin|xing|talent.com|arbeitnow|careers|web",
        "tier": 1, "fit": 7, "priority": 9, "band": "A|B", "lang_line": "exact sentence from the posting",
        "referral": False,
        "recruiter": False, "contact": "consultant name, email, phone when recruiter",
        "salary": "the band the posting states, in its own numbers; '' when it states none",
        "size_class": "startup|mid|large|public|recruiter: startup under 50 staff, mid 50 to 1,000, large 1,000+, public for public sector and research, recruiter when the client is not named",
        "staff": "the headcount you found, e.g. '~30' or '28,000 (group)', '' if unknown",
        "staff_source": "where the headcount comes from: 'their own site', 'their LinkedIn page', 'the posting', 'company cache'. Never a search-result summary",
        "bonus": "the source bonus from instructions/PROFILE.md as a number (0 to 5). write_pack.py adds fit and freshness itself",
        "why": "", "gaps": "", "company_note": "",
        "apply_url": "employer's own posting, the one he should open",
        "employer_site": "", "fallback_url": "aggregator or BA copy", "linkedin_url": "", "xing_url": "", "ba_url": "",
        "cv_base": "CV|LLM|Agentic|Res", "desc": "the description as read (the readers trim perk sentences and diversity boilerplate; everything else verbatim)",
    }],
    "also_found": [{"company": "", "title": "", "location": "", "fit": 6, "band": "A", "url": "", "note": ""}],
    "direct_look": [{"company": "", "what": "", "url": ""}],
    "coverage": [{"source": "", "checked": "yes", "found": 0, "passed": 0, "note": ""}],
    "repeats_skipped": 0, "applied_skipped": 0, "phd_set_aside": 0,
    "candidates": 0, "read_full": 0, "left_unread": 0, "unread_by_source": {"linkedin": 0},
    "rejected_before": 0, "german_dropped": 0, "title_dropped": 0, "minutes": 0,
    "notes": "text under the coverage table: dead boards, blocks, bugs found",
    "rejected": [{"company": "", "title": "", "fit": 4, "gate": "german|clearance|years|phd|non_software|lead|field|closed|repeat|unpaid|no_text",
                  "reason": "one line, quoting the posting where the gate is a line in it"}],
    "borderline": [{"company": "", "title": "", "fit": 5, "url": "", "reason": "one line on the doubt"}],
}

BAND_TITLE = {"A": "Band A, little or no German", "B": "Band B, B1 or more German"}
REFERRAL_TITLE = "Referral first, he has a contact here" 
CV_BASE_HINT = {"CV": "computer vision base CV", "LLM": "LLM systems base CV",
                "Agentic": "agentic and voice base CV", "Res": "research base CV"}


def people_url(company):
    q = urllib.parse.quote("%s machine learning" % company)
    return "https://www.linkedin.com/search/results/people/?keywords=%s" % q


def live(url):
    if not url:
        return "UNSURE", "no url"
    p = subprocess.run([sys.executable, os.path.join(HERE, "check_live.py"), url],
                       capture_output=True, text=True)
    line = (p.stdout.strip().splitlines() or ["UNSURE ?"])[0]
    m = re.match(r"^(\S+)\s+(.*?)\s+(\S+)$", line)
    return (m.group(1), m.group(2).strip()) if m else ("UNSURE", line[:60])


# Sites that list other employers' jobs. A link there is a copy, not the employer's own posting.
JOB_BOARDS = re.compile(r"(^|\.)(linkedin\.com|xing\.com|stepstone\.de|arbeitnow\.com|talent\.com|arbeitsagentur\.de|indeed\.com"
                        r"|glassdoor\.[a-z.]+|jobvector\.de|kimeta\.de|jooble\.org|getro\.com|joblift\.de|monster\.de|jobware\.de"
                        r"|heyjobs\.co|workwise\.io|jobgether\.com|get-in-it\.de|stellenanzeigen\.de|karriere\.at|absolventa\.de)$", re.I)
# Sources whose date is the day the board listed the job, not the day the employer opened it.
LISTING_ONLY = ("linkedin", "xing", "talent.com", "arbeitnow", "stepstone")
RELIST_DAYS = 14


def on_job_board(url):
    try:
        return bool(JOB_BOARDS.search(urllib.parse.urlparse(url or "").netloc.lower()))
    except ValueError:
        return False


def date_remark(j):
    """What stands behind `posted` in the email (docs/PROBLEMS.md 6.3). On 2 Oct, 7 of 20 "new" jobs were old
    ones listed again: Reply's "4 hours old" job dated from 13 May, ElevenLabs' from December 2024."""
    listed, posted = (j.get("posted_listing") or "")[:10], (j.get("posted") or "")[:10]
    if "posted_listing" in j:
        try:
            gap = (datetime.date.fromisoformat(listed) - datetime.date.fromisoformat(posted)).days
        except ValueError:
            gap = None
        if gap is not None and gap >= RELIST_DAYS:
            return " on the employer's board. RELISTED: the job board showed %s, %d days later" % (listed, gap)
        return " (employer board; the listing said %s)" % (listed or "no date")
    if posted and (j.get("source") or "").lower().startswith(LISTING_ONLY) and not j.get("_date_note"):
        return " (the job board's date; the employer's own date was not found, so this may be a relisting)"
    return ""


def job_block(n, j, pack_path):
    lines = []
    lines.append("%d. **%s — %s**%s%s" % (n, j["title"], j["company"],
                                        "  [REFERRAL, ask your contact first]" if j.get("referral") else "",
                                        "  [recruiter posting]" if j.get("recruiter") else ""))
    lines.append("   %s · %s · posted %s%s" % (j.get("location", ""), j.get("employment", "") or "type not stated",
                                               j.get("posted") or "date not found", date_remark(j)))
    lines.append("   Salary: %s" % (j.get("salary") or "not stated in the posting"))
    fig, why = salary.ask(j.get("size_class") or ("recruiter" if j.get("recruiter") else ""), j.get("salary"))
    if fig:
        lines.append("   Ask for: %s (%s%s%s)" % (fig, why, "; this one has %s" % j["staff"] if j.get("staff") else "",
                                                 ", headcount from %s" % j["staff_source"] if j.get("staff") and j.get("staff_source")
                                                 else ", headcount NOT CHECKED, so check the size before you name a figure" if j.get("staff") else ""))
    lines.append("   Fit %s/10 · Priority %s · Tier %s · Source %s" % (j.get("fit"), j.get("priority"),
                                                                       j.get("tier"), j.get("source", "")))
    lines.append("   German: %s" % (j.get("lang_line") or "no language line in the posting"))
    lines.append("   Why it fits: %s" % j.get("why", ""))
    lines.append("   Gaps: %s" % (j.get("gaps") or "none worth worrying about"))
    if j.get("recruiter"):
        lines.append("   Recruiter: %s" % (j.get("contact") or "no contact given in the posting"))
    lines.append("   Company: %s" % j.get("company_note", ""))
    lines.append("   Apply: %s%s" % (j.get("apply_url", ""),
                                    "  [a job board copy, the employer's own posting was not found]" if on_job_board(j.get("apply_url")) else ""))
    extra = []
    if j.get("employer_site"):
        extra.append("employer site %s" % j["employer_site"])
    if j.get("fallback_url") and j["fallback_url"] != j.get("apply_url"):
        extra.append("fallback copy %s" % j["fallback_url"])
    if j.get("linkedin_url") and j["linkedin_url"] != j.get("apply_url"):
        extra.append("LinkedIn %s" % j["linkedin_url"])
    if extra:
        lines.append("   Links: " + " · ".join(extra))
    lines.append("   People at the company: %s" % people_url(j["company"]))
    for r in (j.get("_prior") or [])[:3]:
        lines.append("   Sent before: %s, %s, fit %s, priority %s%s" % (
            r.get("sent"), r.get("title", "")[:50], r.get("fit", "?"), r.get("priority", "?"),
            " (SAME ROLE)" if r.get("same_role") else " (same company, other role)"))
    lines.append("   CV base: %s · Pack: %s · Live at send: %s"
                 % (CV_BASE_HINT.get(j.get("cv_base", ""), j.get("cv_base", "")), pack_path, j.get("_live", "")))
    return "\n".join(lines)


def pack_text(j, sl, pack_id):
    fm = {
        "id": pack_id, "sent": sl["date"], "slot": sl["slot"], "company": j["company"], "title": j["title"],
        "location": j.get("location", ""), "employment": j.get("employment", ""), "posted": j.get("posted", ""),
        "posted_listing": j.get("posted_listing", ""), "date_note": j.get("_date_note", ""),
        "source": j.get("source", ""), "tier": j.get("tier"), "fit": j.get("fit"), "priority": j.get("priority"),
        "band": j.get("band"), "salary": j.get("salary", ""),
        "salary_ask": " ".join(x for x in salary.ask(j.get("size_class") or ("recruiter" if j.get("recruiter") else ""),
                                                      j.get("salary"))[:1] if x),
        "size_class": j.get("size_class", ""), "staff": j.get("staff", ""),
        "lang_line": j.get("lang_line", ""), "recruiter": bool(j.get("recruiter")),
        "referral": bool(j.get("referral")),
        "contact": j.get("contact", ""), "apply_url": j.get("apply_url", ""),
        "employer_site": j.get("employer_site", ""), "fallback_url": j.get("fallback_url", ""),
        "linkedin_url": j.get("linkedin_url", ""), "xing_url": j.get("xing_url", ""), "ba_url": j.get("ba_url", ""),
        "people_url": people_url(j["company"]), "cv_base": j.get("cv_base", ""),
        "live_at_send": j.get("_live", ""),
        "prior_sent": j.get("_prior") or [],
    }
    out = ["---"]
    for k, v in fm.items():
        out.append("%s: %s" % (k, json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v))
    out.append("---")
    out.append("")
    out.append("# %s — %s" % (j["title"], j["company"]))
    out.append("")
    out.append("## Radar verdict")
    out.append("Why it fits: %s" % j.get("why", ""))
    out.append("Gaps: %s" % (j.get("gaps") or "none worth worrying about"))
    out.append("Company: %s" % j.get("company_note", ""))
    out.append("German: %s" % (j.get("lang_line") or "no language line in the posting"))
    out.append("")
    out.append("## Links")
    out.append("Apply here: %s" % j.get("apply_url", ""))
    for k, lab in [("employer_site", "Employer site"), ("fallback_url", "Fallback copy"),
                   ("linkedin_url", "LinkedIn"), ("xing_url", "XING"), ("ba_url", "Bundesagentur")]:
        if j.get(k):
            out.append("%s: %s" % (lab, j[k]))
    out.append("People at the company: %s" % people_url(j["company"]))
    out.append("")
    out.append("## Full job description (as read by the radar on %s)" % sl["date"])
    out.append("")
    out.append(j.get("desc") or "(the radar could not read the description; scrape the apply url locally)")
    out.append("")
    return "\n".join(out)


def reindex(root):
    """jobs/index.json: one object per pack, front matter as JSON, newest first."""
    idx = []
    jd = os.path.join(root, "jobs")
    for f in sorted(os.listdir(jd)):
        if not f.endswith(".md"):
            continue
        txt = open(os.path.join(jd, f), encoding="utf-8").read()
        head = txt.split("\n---\n", 1)[0]
        fm = {}
        for l in head.split("\n")[1:]:
            k, _, v = l.partition(": ")
            if not k:
                continue
            try:
                fm[k] = json.loads(v) if v[:1] in "[{" or v in ("true", "false", "null") or re.fullmatch(r"-?\d+", v) else v
            except Exception:
                fm[k] = v
        fm["pack"] = "jobs/" + f
        idx.append(fm)
    def _prio(x):
        try:
            return float(x.get("priority") or 0)
        except (TypeError, ValueError):
            return 0.0
    idx.sort(key=lambda x: (str(x.get("sent", "")), _prio(x)), reverse=True)
    json.dump(idx, open(os.path.join(jd, "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return idx


def slot_problem(sl, path):
    """Why this shortlist must not be rendered, or None.

    29 Sep 2026, with the noon run. The file name comes from `date` and `slot` in shortlist.json,
    which the agent writes by hand. A noon run that called itself "morning" would overwrite the
    morning's shortlist and its Rejected list, send a correction email, and leave the next noon
    run no record of what the morning read. collect_all.py writes run_slot.json into the scratch
    directory when collection starts, so a run that renders after a slot boundary still matches.
    A shortlist with no run_slot.json beside it (a laptop backfill) is not checked."""
    rec = os.path.join(os.path.dirname(os.path.abspath(path)), "run_slot.json")
    if not os.path.exists(rec):
        return None
    want = json.load(open(rec, encoding="utf-8"))
    got = {"date": sl.get("date"), "slot": sl.get("slot")}
    if got != {"date": want.get("date"), "slot": want.get("slot")}:
        return ("REFUSED: shortlist.json says %s %s, but this run collected as %s %s (run_slot.json). "
                "Fix date and slot in shortlist.json and render again." % (got["date"], got["slot"],
                                                                           want.get("date"), want.get("slot")))
    return None


def main():
    if sys.argv[1] == "--reindex":
        n = len(reindex(os.path.dirname(HERE)))
        print("jobs/index.json rebuilt, %d packs" % n)
        return
    path = sys.argv[1]
    sl = json.load(open(path, encoding="utf-8"))
    bad = slot_problem(sl, path)
    if bad:
        sys.exit(bad)
    # 30 Sep 2026: the run time comes from the clock, not from the agent (slots.elapsed_minutes).
    mins = elapsed_minutes(os.path.dirname(os.path.abspath(path)))
    if mins is not None:
        sl["minutes"] = mins
    root = os.path.dirname(HERE)
    # 29 Sep 2026 review: the agent writes this file by hand, so shapes vary. A string priority
    # crashed the redate step, a float one crashed reindex on every later run, and a string in
    # also_found crashed rendering after state/seen.json was written. Normalise before anything runs.
    def _num(v):
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return 0
    for key in ("jobs", "also_found", "direct_look", "rejected", "coverage", "borderline"):
        v = sl.get(key)
        if v is None:
            continue
        if not isinstance(v, list):
            v = [v]
        sl[key] = [x if isinstance(x, dict) else {"title": str(x)} for x in v]
    sl["jobs"] = [j for j in sl.get("jobs", []) if j.get("company") or j.get("title")]
    for j in sl.get("jobs", []):
        j["company"], j["title"] = str(j.get("company") or "?"), str(j.get("title") or "?")
        for k in ("fit", "priority"):
            if j.get(k) not in (None, ""):
                j[k] = _num(j[k])
    date, slot = sl["date"], sl["slot"]
    jobs = sl.get("jobs", [])
    # 2 Oct 2026: what was read is taken from the reader's log (scripts/read_next.py), never from the
    # agent. A job the reader did not print in full is not sent. The rejected, borderline and fit-6
    # lists and the reading counts come from verdicts.json. A render without a reader log (a laptop
    # backfill, --packs-only) is not checked.
    sc_dir = os.path.dirname(os.path.abspath(path))
    verdicts_used = None
    import verdict as V
    if V.no_reader(sc_dir):
        sys.exit("REFUSED: %s. Nothing was written." % V.NO_READER)
    if os.path.exists(os.path.join(sc_dir, "read_log.json")):
        import read_next as RN
        notread = V.unread_jobs(sc_dir, jobs)
        if notread:
            for j, why in notread:
                print("NOT READ %s | %s: %s" % (j["company"], j["title"][:60], why), file=sys.stderr)
            sys.exit("REFUSED: %d of the %d jobs to send were not read in full by scripts/read_next.py. Nothing was "
                     "written. Read them, or take them out of `jobs`, and render again." % (len(notread), len(jobs)))
        built = V.lists(sc_dir)
        for key in ("also_found", "borderline", "rejected"):
            sl[key] = built[key]
        sl.update(V.counts(sc_dir))
        sl["reading"] = V.reading_record(sc_dir)        # 3 Oct 2026: kept for scripts/read_audit.py
        full = {RN.cid(c): c.get("desc") or "" for c in RN.candidates(sc_dir)}
        for j in jobs:
            j["desc"] = full.get(j.get("id")) or j.get("desc") or ""      # the text that was read, whole
        verdicts_used = RN.verdicts(sc_dir)
    # 2 Oct 2026 (docs/PROBLEMS.md 5.6): the final check is part of the render. On 30 Sep the noon run
    # rendered 20 jobs, found a repeat afterwards (knuspr is Rohlik), and a second email went out seven
    # minutes later. Nothing is written or pushed while a job in the list must go.
    if "--packs-only" not in sys.argv and "--no-final-check" not in sys.argv:
        import final_check
        try:
            tmp = dict(sl, jobs=jobs)
            fc_path = os.path.join(sc_dir, ".final_check.json")
            json.dump(tmp, open(fc_path, "w", encoding="utf-8"), ensure_ascii=False)
            must_go = [r for r in final_check.check(fc_path, root) if r[0] in final_check.BAD]
            os.remove(fc_path)
        except Exception as ex:
            must_go = []
            print("final check could not run inside the render: %s. Run scripts/final_check.py by hand." % str(ex)[:120], file=sys.stderr)
        if must_go:
            for verdict_, co, ti, note in must_go:
                print("%-10s %s | %s  %s" % (verdict_, co[:40], ti[:60], note[:160]), file=sys.stderr)
            sys.exit("REFUSED: %d jobs must leave the list before the render (see the lines above and scripts/final_check.py). "
                     "Nothing was written, so no email goes out. Fix shortlist.json and render again." % len(must_go))
    dropped = []
    for j in jobs:
        st, why = live(j.get("apply_url") or j.get("fallback_url"))
        j["_live"] = "%s (%s)" % (st, why)
        if st == "GONE":
            dropped.append(j)
    jobs = [j for j in jobs if j not in dropped]
    # 8 Sep 2026: LinkedIn and XING card dates are re-listing dates. Take the employer board's
    # date whenever one can be read, and move the freshness bonus with it.
    for j in jobs:
        for u in (j.get("apply_url"), j.get("fallback_url")):
            if not u or "linkedin.com" in u or "xing.com" in u:
                continue
            d, note = true_date(u, j.get("title", ""))
            if d:
                if d != (j.get("posted") or "")[:10]:
                    j["posted_listing"] = j.get("posted") or ""
                    old_b, new_b = freshness(j.get("posted"), date), freshness(d, date)
                    j["priority"] = (j.get("priority") or 0) - old_b + new_b
                    j["posted"] = d
                    j["_date_note"] = "%s; the listing said %s" % (note, j["posted_listing"] or "no date")
                    print("REDATED %s | %s: %s -> %s (%s), priority %+d" % (
                        j["company"], j["title"][:40], j["posted_listing"] or "-", d, note, new_b - old_b), file=sys.stderr)
                else:
                    j["_date_note"] = note
                break
    # 2 Oct 2026 (docs/TODO.md task 3 of 29 Sep): priority = fit + freshness of the final date + the source
    # bonus the agent gives in `bonus`. The agent used to add the freshness itself and skipped the -2 for
    # "no date", so a redated job gained up to 4 points (logen.ai: correct 11, shown 14). A job without
    # `bonus` keeps the priority it came with, moved by the redating above.
    for j in jobs:
        if j.get("bonus") not in (None, ""):
            j["priority"] = (j.get("fit") or 0) + freshness(j.get("posted"), date) + _num(j["bonus"])
    # Headcount (docs/PROBLEMS.md 4.6). A size from the company cache is used when the agent gave none, and
    # what the agent found goes back into the cache with where it came from.
    for j in jobs:
        try:
            cached = company_cache.get(j["company"]) or {}
        except Exception:
            cached = {}
        if not j.get("staff") and cached.get("staff"):
            j["staff"], j["size_class"] = cached["staff"], j.get("size_class") or cached.get("size_class", "")
            j["staff_source"] = "company cache, %s" % (cached.get("staff_source") or cached.get("updated", ""))
    # 2 Oct 2026 (docs/PROBLEMS.md 3.6): a conditional clearance line does not stop a job, and it must not be
    # lost either. The sentence is added to Gaps when the agent's text does not already carry it.
    import clearance
    for j in jobs:
        if j.get("referral"):
            continue
        cv, clines = clearance.check(j.get("desc") or "")
        if cv == "flag" and clines[0][:40] not in (j.get("gaps") or ""):
            j["gaps"] = ("%s %s" % ((j.get("gaps") or "").strip(), clearance.gap_text(clines))).strip()
    # Salary. Added 21 Sep 2026. The agent fills `salary` from the posting; this reads the
    # description independently and fills the field when the agent left it empty, the same way
    # the dates above are taken from the board rather than trusted. About one posting in six
    # states a band at all (13 of the last 80 packs), so an empty field is the normal case and
    # never an error. Nothing is ever estimated.
    for j in jobs:
        found = salary.extract(j.get("desc") or "")
        stated = (j.get("salary") or "").strip()
        if not stated and found:
            j["salary"] = found
            print("SALARY %s | %s: %s (read from the description)" % (
                j["company"], j["title"][:40], found), file=sys.stderr)
        elif stated and found and not (salary.numbers(stated) & salary.numbers(found)):
            # Two different bands in the same posting is usually a US range beside a European
            # one. The agent's reading wins, and the disagreement is printed so the run report
            # can mention it.
            print("SALARY MISMATCH %s | %s: shortlist says %s, the description says %s" % (
                j["company"], j["title"][:40], stated, found), file=sys.stderr)

    for j in dropped:
        print("DROPPED, gone at send: %s | %s | %s" % (j["company"], j["title"], j.get("apply_url")), file=sys.stderr)
    sl["jobs"] = jobs

    # packs + seen
    seen = json.load(open(os.path.join(root, "state/seen.json")))
    seen_ids = {e.get("id") for e in seen}
    # 8 Sep 2026: Audatic was sent on 15 Aug (as "Sonova", fit 7, priority 5, from talent.com) and
    # again on 8 Sep (as "Audatic", fit 9, priority 10, from LinkedIn) and nobody noticed. Every job
    # now carries its prior appearances, same role first, then anything else at the company.
    prior_pool = [e for e in seen if e.get("sent") != date]
    for j in jobs:
        same_role = is_repeat(j["company"], j["title"], j.get("location", ""), prior_pool,
                              j.get("apply_url") or j.get("fallback_url") or "", j.get("desc") or "")
        rows = []
        if same_role:
            rows.append(dict(sent=same_role.get("sent") or same_role.get("date", ""), title=same_role.get("title", ""),
                             company=same_role.get("company", ""), fit=same_role.get("fit"),
                             priority=same_role.get("priority"), same_role=True))
        for e in prior_pool:
            if e is same_role:
                continue
            te, tj = company_tokens(e.get("company", "")), company_tokens(j["company"])
            if te and tj and (te <= tj or tj <= te
                              or len(te & tj) / min(len(te), len(tj)) >= 0.6):
                rows.append(dict(sent=e.get("sent") or e.get("date", ""), title=e.get("title", ""),
                                 company=e.get("company", ""), fit=e.get("fit"), priority=e.get("priority"),
                                 same_role=False))
        rows.sort(key=lambda r: r.get("sent") or "", reverse=True)
        j["_prior"] = rows[:6]
        if same_role:
            print("PRIOR SAME ROLE %s | %s: sent %s as '%s' fit %s priority %s" % (
                j["company"], j["title"][:40], same_role.get("sent"), same_role.get("company"),
                same_role.get("fit"), same_role.get("priority")), file=sys.stderr)
    packs = {}
    for j in jobs:
        pid = canonical_id(j["company"], j["title"], j.get("location", ""))
        rel = "jobs/%s.md" % pid
        open(os.path.join(root, rel), "w", encoding="utf-8").write(pack_text(j, sl, pid))
        packs[pid] = rel
        j["_pack"] = rel
        entry = dict(id=pid, company=j["company"], title=j["title"], location=j.get("location", ""),
                     url=j.get("apply_url") or j.get("fallback_url", ""), fit=j.get("fit"), sent=date, slot=slot,
                     urls=sorted({u for u in (j.get(k) for k in ("apply_url", "fallback_url", "ba_url", "linkedin_url",
                                                                   "xing_url", "url")) if u}),
                     band=j.get("band"), pack=rel, source=j.get("source", ""), priority=j.get("priority"),
                     posted=j.get("posted", ""))
        try:
            company_cache.upsert(j["company"], dict(
                site=j.get("employer_site", ""), careers_url=j.get("employer_site", ""),
                board=board_of(j.get("apply_url")) or board_of(j.get("fallback_url")),
                what=j.get("company_note", ""), language=j.get("lang_line", ""),
                staff=j.get("staff", "") if j.get("staff_source") and not str(j.get("staff_source")).startswith("company cache") else "",
                size_class=j.get("size_class", "") if j.get("staff_source") and not str(j.get("staff_source")).startswith("company cache") else "",
                staff_source=j.get("staff_source", "") if not str(j.get("staff_source") or "").startswith("company cache") else "",
                last_seen=date, sources=[j.get("source", "")],
                sent=[dict(date=date, title=j["title"], fit=j.get("fit"), priority=j.get("priority"))]), by="cloud")
        except Exception as ex:
            print("company cache skipped for %s: %s" % (j["company"], str(ex)[:60]), file=sys.stderr)
        if pid in seen_ids:
            seen = [e for e in seen if e.get("id") != pid]
        seen.append(entry)
    cutoff = (datetime.date.fromisoformat(date) - datetime.timedelta(days=90)).isoformat()
    seen = [e for e in seen if (e.get("sent") or e.get("date") or "9999") >= cutoff]
    # --packs-only (29 Sep 2026): add jobs to his pool without a shortlist, so no email goes out.
    # Used to backfill jobs a run found but never sent. state/seen.json still records them, so no later
    # run sends them again, and pick.py and batch mode see them like any other pack.
    if "--packs-only" in sys.argv:
        json.dump(seen, open(os.path.join(root, "state/seen.json"), "w"), ensure_ascii=False, indent=1)
        reindex(root)
        print("%d packs written without a shortlist (no email), state/seen.json now %d entries, %d dropped as gone"
              % (len(packs), len(seen), len(dropped)), file=sys.stderr)
        return
    # state/seen.json is written at the very end, after the shortlist files exist. Written here, a crash
    # while rendering marked jobs as sent that were never emailed (review, 29 Sep 2026).

    # email
    n_new = len(jobs)
    md = ["# Job radar, %s %s, %d new" % (date, slot, n_new), ""]
    if sl.get("intro"):
        md += [sl["intro"], ""]
    order = sorted(jobs, key=lambda j: -(j.get("priority") or 0))
    n = 0
    ref = [j for j in order if j.get("referral")]
    if ref:
        md += ["## %s (%d)" % (REFERRAL_TITLE, len(ref)), ""]
        for j in ref:
            n += 1
            md += [job_block(n, j, j["_pack"]), ""]
    for band in ("A", "B"):
        group = [j for j in order if (j.get("band") or "A") == band and not j.get("referral")]
        md.append("## %s (%d)" % (BAND_TITLE[band], len(group)))
        md.append("")
        if not group:
            md += ["Nothing new in this band this run.", ""]
        for j in group:
            n += 1
            md += [job_block(n, j, j["_pack"]), ""]
    # 30 Sep 2026: a fresh job in his field that the run did not read is listed here with its link, so
    # a run cut short (time, usage limit) never hides one. scripts/fresh_check.py finds them. This
    # section must never stop the email, so any error only leaves a note.
    try:
        import fresh_check
        left = fresh_check.unread_fresh(os.path.dirname(os.path.abspath(path)), sl)
        if left:
            md += ["## Fresh, not read yet (%d)" % len(left), "",
                   "Posted in the last %d days, in your field, and not read by this run. Open these first."
                   % cfg.get("reading", "must_read_days"), ""]
            for c in left:
                md.append("- %s · %s | %s · %s" % ((c.get("date") or "")[:10], c.get("company") or "?",
                                                    c.get("title") or "?", c.get("url") or "no link"))
            md.append("")
            print("FRESH NOT READ: %d, listed in the email" % len(left), file=sys.stderr)
    except Exception as ex:
        md += ["Fresh, not read yet: could not be checked (%s)" % str(ex)[:80], ""]
    # 2 Oct 2026: a job with no text was not read, so it is neither sent nor rejected. It is listed
    # here with its link and the reason, for him to open. On 2 Oct three such jobs were sent as
    # "Tier 3", one of them a NATO-nationality role.
    if verdicts_used is not None:
        try:
            why = {r.get("url"): r.get("why") for r in json.load(open(os.path.join(sc_dir, "no_text.json"), encoding="utf-8"))} \
                if os.path.exists(os.path.join(sc_dir, "no_text.json")) else {}
            blind = [c for c in RN.candidates(sc_dir) if not RN.has_text(c)]
            if blind:
                md += ["## Could not be read (%d)" % len(blind), "",
                       "The radar found no text for these, so nobody read them. They are not judged. Open the ones whose title fits.", ""]
                for c in blind:
                    md.append("- %s | %s · %s · %s" % (c.get("company") or "?", c.get("title") or "?", c.get("url") or "no link",
                                                       (why.get(c.get("url")) or "no text at the source")[:110]))
                md.append("")
        except Exception as ex:
            md += ["Could not be read: the list could not be built (%s)" % str(ex)[:80], ""]
    # 30 Sep 2026: a job is rejected only for a named gate (instructions/PROFILE.md, "When to reject"). Borderline
    # jobs, and any rejection that names no valid gate, are listed for him to decide.
    border = list(sl.get("borderline") or []) + [r for r in sl.get("rejected") or [] if r.get("gate") not in GATES]
    if border:
        links = {}
        for c in json.load(open(os.path.join(os.path.dirname(os.path.abspath(path)), "candidates.json"), encoding="utf-8")) \
                if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(path)), "candidates.json")) else []:
            links.setdefault(canonical_id(c.get("company") or "", c.get("title") or "", ""), c.get("url") or "")
        md += ["## Borderline, not sent (%d)" % len(border), "",
               "Read in full and close to the bar, with no clear reason to reject. Your call.", ""]
        for r in border:
            link = r.get("url") or r.get("apply_url") or links.get(canonical_id(r.get("company") or "", r.get("title") or "", ""), "")
            md.append("- %s | %s · fit %s · %s%s" % (r.get("company") or "?", r.get("title") or "?", r.get("fit", "?"),
                                                    r.get("reason") or r.get("doubt") or "no reason given",
                                                    (" · " + link) if link else ""))
        md.append("")
    if sl.get("also_found"):
        # 2 Oct 2026 (the candidate): every job at fit 7 or higher is sent in full, with no cap. Fit 6 is one line.
        md += ["## Fit 6, one line each (%d)" % len(sl["also_found"]), ""]
        for a in sl["also_found"]:
            md.append("- %s — %s · %s · fit %s · band %s · %s%s" % (
                a.get("title", ""), a.get("company", ""), a.get("location", ""), a.get("fit", "?"),
                a.get("band", "?"), a.get("url", ""), (" · " + a["note"]) if a.get("note") else ""))
        md.append("")
    if sl.get("direct_look"):
        md += ["## Companies worth a direct look", ""]
        for d in sl["direct_look"]:
            md.append("- **%s** — %s %s" % (d.get("company", ""), d.get("what", ""), d.get("url", "")))
        md.append("")
    # 2 Oct 2026 (docs/PROBLEMS.md 6.1): the email ends here. The emails of 30 Sep to 2 Oct were 440 to 550
    # lines. Everything below this heading stays in the file and in reports/LATEST.md, and send_mail.py cuts it
    # off: the coverage table, the health flags, the notes and the rejected list.
    boards = sum(1 for j in jobs if on_job_board(j.get("apply_url")))
    md += ["Read in full: %s of %s candidates. Not read again, read by an earlier run: %s. No text, not read: %s. "
           "Apply links that are a job board copy: %d of %d. Run time: about %s minutes. Details: shortlists/%s-%s.md"
           % (sl.get("read_full", "?"), sl.get("candidates", "?"), sl.get("remembered", "?"), sl.get("no_text", "?"),
              boards, len(jobs), sl.get("minutes", "?"), date, slot), ""]
    # 7 Oct 2026: per-source funnel with the text check, above the cut so it is in the email.
    try:
        import health
        fl = health.funnel_lines(health.latest_record(date, slot), jobs)
        if fl:
            md += ["Where the jobs went (text = 300+ characters of description):"] + ["- %s" % l for l in fl] + [""]
    except Exception as ex:
        md += ["Source funnel could not be read (%s)" % str(ex)[:60], ""]
    md += ["## Run details", "",
           "This part is not in the email.", ""]
    md += ["### Source coverage", "", "    %-34s %-8s %7s %11s  %s" % ("Source", "Checked", "Found", "Passed fit", "Note")]
    for c in sl.get("coverage", []):
        md.append("    %-34s %-8s %7s %11s  %s" % (c.get("source", ""), c.get("checked", ""),
                                                c.get("found", ""), c.get("passed", ""), c.get("note", "")))
    md.append("")
    md.append("Repeats skipped: %s. Already-applied companies skipped: %s. PhD and student roles set aside: %s."
              % (sl.get("repeats_skipped", "?"), sl.get("applied_skipped", "?"), sl.get("phd_set_aside", "?")))
    # 29 Sep 2026: what the run read and what it left, so the case for a third run is measured.
    if "read_full" in sl:
        ub = sl.get("unread_by_source") if isinstance(sl.get("unread_by_source"), dict) else {}
        def _n(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0
        ub = {str(k): _n(v) for k, v in ub.items()}
        md.append("Candidates after filters: %s. Dropped by title triage: %s. Read in full: %s. Left unread: %s%s. "
                  "Skipped as rejected before: %s. German dropped unread: %s. Run time: about %s minutes."
                  % (sl.get("candidates", "?"), sl.get("title_dropped", "?"), sl.get("read_full", "?"), sl.get("left_unread", "?"),
                     " (%s)" % ", ".join("%s %s" % (k, v) for k, v in sorted(ub.items(), key=lambda x: -x[1]) if v) if ub else "",
                     sl.get("rejected_before", "?"), sl.get("german_dropped", "?"), sl.get("minutes", "?")))
        if verdicts_used is not None:
            md.append("Read in full is counted by the reader, not reported by the run. Without text and so not read: %s. "
                      "Read by an earlier run and not read again: %s." % (sl.get("no_text", 0), sl.get("remembered", "?")))
    # 29 Sep 2026: flags from scripts/health.py for this run, printed without the agent's help.
    try:
        import health
        hf = health.latest_flags(date, slot)
        if hf is not None:
            md.append("")
            md.append("Source health: %s" % ("no flags" if not hf else ""))
            md += ["- %s" % f for f in hf]
    except Exception as ex:
        md.append("Source health: could not be read (%s)" % str(ex)[:60])
    if dropped:
        md.append("Dropped at the final liveness check because the posting was gone: %s."
                  % "; ".join("%s (%s)" % (d["company"], d["title"]) for d in dropped))
    if sl.get("notes"):
        md += ["", sl["notes"]]
    md.append("")
    md.append("Packs for every job above are in `jobs/`. On the laptop: `python3 ~/job_hunt/scripts/pick.py` lists them, `pick.py <n>` loads one.")
    md.append("")
    if sl.get("rejected"):
        md += ["## Rejected", ""]
        for r in sl["rejected"]:
            md.append("- %s — %s · fit %s · %s%s" % (r.get("title", ""), r.get("company", ""), r.get("fit", "?"),
                                                    "gate %s · " % r["gate"] if r.get("gate") else "", r.get("reason", "")))
        md.append("")
    out = os.path.join(root, "shortlists", "%s-%s.md" % (date, slot))
    open(out, "w", encoding="utf-8").write("\n".join(md))
    # 29 Sep 2026: remember German and clearance kills so filter_run.py skips them next time.
    try:
        import rejected as rejmem
        rrows = rejmem.load()
        n_rej = rejmem.merge(rrows, sl.get("rejected"), date)
        rejmem.save(rrows)
        print("state/rejected.json: %d new German or clearance kills, %d entries" % (n_rej, len(rrows)), file=sys.stderr)
    except Exception as ex:
        print("state/rejected.json not updated: %s" % str(ex)[:80], file=sys.stderr)
    # 2 Oct 2026: every verdict of this run goes into state/decisions.json, so the next runs do not read
    # these jobs again (scripts/decisions.py).
    if verdicts_used is not None:
        try:
            import decisions
            import read_next as RN
            n_dec = decisions.record(verdicts_used, RN.candidates(sc_dir), date, slot, root)
            print("state/decisions.json: %d verdicts stored" % n_dec, file=sys.stderr)
        except Exception as ex:
            print("DECISIONS NOT STORED: %s. Say so in the notes." % str(ex)[:120], file=sys.stderr)
    # 29 Sep 2026: the leftover list the noon run works from (scripts/leftover.py). Morning and
    # evening add what they did not read; noon removes what it processed.
    try:
        import leftover
        msg = leftover.after_render(os.path.dirname(os.path.abspath(path)), sl, root)
        if msg:
            print(msg, file=sys.stderr)
    except Exception as ex:
        print("LEFTOVER NOT UPDATED: %s. Say so in the notes." % str(ex)[:120], file=sys.stderr)
    # 8 Sep 2026: the same rows as JSON, so the laptop never parses the markdown again.
    rows = []
    for j in jobs:
        r = {k: v for k, v in j.items() if not k.startswith("_") and k != "desc"}
        r.update(id=os.path.basename(j["_pack"])[:-3], pack=j["_pack"], live_at_send=j.get("_live", ""),
                 prior_sent=j.get("_prior") or [], date_note=j.get("_date_note", ""))
        rows.append(r)
    run = {k: v for k, v in sl.items() if k not in ("jobs", "rejected")}
    run["jobs"] = rows
    json.dump(run, open(out[:-3] + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(seen, open(os.path.join(root, "state/seen.json"), "w"), ensure_ascii=False, indent=1)
    # 29 Sep 2026: the per-run health record, readable. After the run JSON so its counts are in.
    try:
        import health
        health.render(root)
    except Exception as ex:
        print("reports/HEALTH.md not rebuilt: %s" % str(ex)[:80], file=sys.stderr)
    reindex(root)
    print(out)
    print("%d jobs rendered (%d band A, %d band B), %d packs, state/seen.json now %d entries, %d dropped as gone"
          % (n_new, sum(1 for j in jobs if (j.get("band") or "A") == "A"),
             sum(1 for j in jobs if j.get("band") == "B"), len(packs), len(seen), len(dropped)), file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--schema":
        print(json.dumps(SHORTLIST_SCHEMA, indent=1, ensure_ascii=False))
    else:
        main()
