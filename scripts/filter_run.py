#!/usr/bin/env python3
"""Filter the collected pools down to ML-relevant, non-repeat candidates."""
import json
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jobid import is_repeat, canonical_id
import cfg
import applications

# Every title, employer and location pattern below is read from config/radar.yaml (29 Sep 2026).

SCRATCH = sys.argv[1]
# Repo root, so the script works from any cwd. collect_all.py calls it from wherever the run
# happens to be, and a relative "state/seen.json" there would raise, while a relative
# "state/applications.md" would silently load nothing and let applied companies through.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
seen = json.load(open(os.path.join(ROOT, "state/seen.json")))

# --- title relevance -------------------------------------------------------
GOOD = cfg.rx("filters", "title_good")
BAD = cfg.rx("filters", "title_bad")
# Titles that are ML-adjacent but explicitly not wanted per instructions/PROFILE.md
NOTWANTED = cfg.rx("filters", "not_wanted")
# 31 Aug 2026 evening: `data engineer` matched inside "Computer Vision & 3D/BIM Data Engineer"
# and threw it away. That was the best-fitting job of the whole run — geometry-aware CV data
# pipelines, semantic segmentation, depth/normal maps, PyTorch/OpenCV — and it only surfaced by
# rescanning the raw Bundesagentur pool by hand. A title carrying a real modelling word is not a
# data-engineering job just because "Data Engineer" also appears in it. So for this family of
# terms only, let the modelling word win; the seniority and management terms above still kill a
# title outright, and a bare "Data Engineer" with no modelling word is still dropped.
DATA_FAMILY = cfg.rx("filters", "data_family")
CORE_ML = cfg.rx("filters", "core_ml")


# 30 Sep 2026 (the candidate): data engineering and anything AI or ML related stays. A title from
# not_wanted_unless_ai (DevOps, platform, consultant, frontend...) is out only when it names no AI,
# ML or data work.
NOTWANTED_UNLESS_AI = cfg.rx("filters", "not_wanted_unless_ai")
AI_OR_DATA = cfg.rx("filters", "ai_or_data")


def notwanted(t):
    t = t or ""
    if NOTWANTED.search(t):
        if not (DATA_FAMILY.search(t) and CORE_ML.search(t)):
            return True
        # Drop the data-family words and see whether anything else still disqualifies.
        if NOTWANTED.search(DATA_FAMILY.sub(" ", t)):
            return True
    return bool(NOTWANTED_UNLESS_AI.search(t)) and not AI_OR_DATA.search(t)


# Bare `staff` used to match here, which threw away every `Member of Technical Staff` title.
# At AI labs that is the standard IC title, not a staff-level one — it silently dropped all
# three Black Forest Labs roles on 6 Aug 2026. Only a real staff-engineer title is out.
SENIOR_OUT = cfg.rx("filters", "senior_out")

# Training providers spam the Bundesagentur with courses dressed as jobs. Always out.
JUNK_EMPLOYER = cfg.rx("filters", "junk_employer")
# Recruiters and agencies used to be in the list above and were dropped outright. Since
# 8 Sep 2026 (instructions/PROFILE.md) they are kept and tagged, because recruiter postings are a real
# channel in Germany. The agent reads them like any other job, caps them at 3 per run, and
# prints the consultant's contact instead of a company write-up.
RECRUITER = cfg.rx("filters", "recruiter")

# Referral companies (instructions/PROFILE.md). The candidate has a contact there, so DHL rows skip the
# not-wanted and seniority title filters and are tagged for the agent to read first.
REFERRAL_CO = cfg.rx("profile", "referral_companies")


def referral(j):
    return bool(REFERRAL_CO.search(j.get("company") or ""))


# PhD and Doktorand positions are off since 8 Sep 2026 (instructions/PROFILE.md). They leave the pool here,
# into phd_off.json, so the run can still count them and the switch is one regex to flip.
PHD_OFF = cfg.rx("filters", "phd_off")

DE_HINT = cfg.rx("filters", "location_ok")
OUT_OF_SCOPE = cfg.rx("filters", "location_out")

APPLIED = list(cfg.get("profile", "applied_companies"))


def applied_from_log(path=None):
    """Company names from the applications log synced by pick.py (8 Sep 2026). One row per
    job researched, company in the second column, plus the comma list under 'Older
    applications'. Generic single words are left out so they cannot match half the pool."""
    path = path or os.path.join(ROOT, "state/applications.md")
    if not os.path.exists(path):
        return []
    names = [r["Company"] for r in applications.rows(path)] + applications.older_names(path)
    skip = {"general", "group", "gmbh", "ag", "se"}
    out = []
    for n in names:
        n = re.sub(r"\s*\(.*?\)", "", n).replace("\\", "").strip().lower().rstrip(".,;")
        n = re.sub(r"\s+(gmbh|ag|se|kgaa|group)$", "", n)
        if len(n) >= 4 and n not in skip:
            out.append(n)
    return out


def applied_roles(path=None):
    """(company, role, date) per log row, for the title match below."""
    path = path or os.path.join(ROOT, "state/applications.md")
    if not os.path.exists(path):
        return []
    return [(r["Company"].lower(), r["Role"], r["Researched"]) for r in applications.rows(path)]


APPLIED_ROLES = applied_roles()
APPLIED += applied_from_log()
# Match these as whole words, not as substrings. A plain `a in company.lower()` reads "tum"
# inside "Quantum-Systems" and "sap" inside "osapiens", and on 11 Aug 2026 evening that was
# silently discarding 380 postings a run — Quantum-Systems' entire 291-posting Recruitee board
# (including "Software Engineer (m/f/d) - Perception" and "AI Computer Vision Engineer"),
# osapiens' 72, QuantumDiamonds, Kipu Quantum and PetsApp. The board was fixed twice before for
# other reasons and still never reached the shortlist, because this check killed it downstream.
APPLIED_RE = re.compile(
    "|".join(r"(?<![a-z])%s(?![a-z])" % re.escape(a) for a in APPLIED), re.I)


def title_ok(t):
    if not t or BAD.search(t) or SENIOR_OUT.search(t):
        return False
    if not GOOD.search(t):
        return False
    return True


# Boards that mean "remote, anywhere" write the location as a single word, which matched no city
# and no country, so loc_ok threw the row out. That hid HiPeople's Applied AI Engineer — Berlin-
# based, board says "World" — and every other role on that board on 8 Aug 2026; it only surfaced by
# rescanning the raw pool by hand. Match this against the location alone, never against the title:
# "Machine Learning Engineer, Global Public Sector" is a Doha and Riyadh job, not a remote one.
ANYWHERE = cfg.rx("filters", "location_anywhere")


def loc_ok(loc, title=""):
    if ANYWHERE.match(loc or ""):
        return True
    s = "%s %s" % (loc or "", title or "")
    if not s.strip():
        return True                     # unknown, keep and check by hand
    if DE_HINT.search(s):
        # a job listing both Berlin and London is fine; pure-foreign is not
        return True
    return not OUT_OF_SCOPE.search(s) and not (loc or "").strip()


def load(name):
    p = os.path.join(SCRATCH, name)
    return json.load(open(p)) if os.path.exists(p) else []


cands = []
phd_off = []


def phd(j):
    if PHD_OFF.search(j.get("title") or ""):
        phd_off.append(dict(company=j.get("company"), title=j.get("title"), url=j.get("url")))
        return True
    return False


def screen(j, junk=True, referral_ok=True, place=True):
    """Why a raw row is out, or None. The one rule for every source (1 Nov 2026; before that each
    source had its own copy of these lines in its own order). A referral row skips the not-wanted
    and seniority filters and only needs an ML word in the title. `junk` is off for the company
    boards and Getro, which carry no training-provider spam. `place` is off for the Bundesagentur,
    whose rows are nationwide by query."""
    title = j.get("title") or ""
    if junk and JUNK_EMPLOYER.search(j.get("company") or ""):
        return "junk employer"
    if referral_ok and referral(j):
        if BAD.search(title) or not GOOD.search(title):
            return "title"
    elif not title_ok(title) or notwanted(title) or phd(j):
        return "title"
    if place and not loc_ok(j.get("location", ""), title):
        return "location"
    return None


def _rec(j):
    return bool(RECRUITER.search(j.get("company") or ""))


import datetime as _dt
# XING's date sort is loose and the pool reaches back a year. The activatedAt date is real, so
# anything older than two weeks is not worth a read here.
XING_CUTOFF = (_dt.date.today() - _dt.timedelta(days=14)).isoformat()

# One line per pool file: the label in the log, the screen flags, the fields the candidate row
# carries beyond the common ones, and a drop rule of its own. Descriptions are kept whole (2 Oct
# 2026): every source used to be cut at 6,000 characters, which took the end of the posting, where
# the language line and the requirements sit.
#   Bundesagentur  cards; the detail is fetched later, hence desc "".
#   Getro          hipeople.io/job-description/<role> urls are HiPeople's marketing templates for a
#                  fictional "ExampleCorp", not openings (5 Aug 2026); the real jobs are on Ashby.
#   talent.com     cards with no description; they hand over a company and title to read at source.
#   arbeitnow      `ingest_date` is arbeitnow's own timestamp, never the employer's posting date, so
#                  `date` is left empty and the freshness bonus comes from the employer's board.
#   LinkedIn       cards; read_linkedin.py fetches the description by li_id.
#   XING           description, real posting timestamp and the employer's own apply url.
#   StepStone      JSON-LD description, employer, real posting date and employment type.
SOURCES = [
    ("ba", "BA", dict(place=False),
     lambda j: dict(source="Bundesagentur", ref=j["ref"], art=j.get("art", ""), desc="", recruiter=_rec(j), referral=referral(j)), None),
    ("ats", "ATS", dict(junk=False),
     lambda j: dict(source="ATS/" + j.get("source", ""), salary=j.get("salary", ""), referral=referral(j)), None),
    ("getro", "Getro", dict(junk=False, referral_ok=False),
     lambda j: dict(source=j.get("source", "getro"), desc="", org_url=j.get("org_url", ""), org_desc=j.get("org_desc", "")),
     lambda j: "hipeople.io/job-description/" in (j.get("url") or "")),
    ("talent", "talent", dict(referral_ok=False),
     lambda j: dict(source="talent.com", age=j.get("age", ""), feed=j.get("feed", ""), desc="", recruiter=_rec(j)), None),
    ("arbeitnow", "arbeitnow", dict(referral_ok=False),
     lambda j: dict(date="", ingest_date=j.get("ingest_date", "")), None),
    ("linkedin", "linkedin", {},
     lambda j: dict(li_id=j.get("li_id", ""), desc="", recruiter=_rec(j), referral=referral(j)), None),
    ("xing", "xing", dict(referral_ok=False),
     lambda j: dict(apply_url=j.get("apply_url", ""), date=(j.get("date") or "")[:10], xing_id=j.get("xing_id", ""),
                    salary=j.get("salary", ""), recruiter=_rec(j)),
     lambda j: (j.get("date") or "")[:10] < XING_CUTOFF),
    ("stepstone", "stepstone", {},
     lambda j: dict(date=(j.get("date") or "")[:10], ss_id=j.get("ss_id", ""), employment=j.get("employment", ""),
                    salary=j.get("salary", ""), recruiter=_rec(j), referral=referral(j)), None),
]

counts = []
for name, label, flags, extra, drop in SOURCES:
    rows = load(name + ".json")
    keep = []
    for j in rows:
        if (drop and drop(j)) or screen(j, **flags):
            continue
        r = dict(source=name, company=j["company"], title=j["title"], location=j.get("location", ""),
                 url=j.get("url", ""), date=j.get("date", ""), desc=j.get("desc") or "")
        r.update(extra(j))
        keep.append(r)
    cands += keep
    counts.append("%s %d / %d" % (label, len(keep), len(rows)))

print("relevance-passed:  " + "   ".join(counts) + "   (phd/student set aside: %d)" % len(phd_off), file=sys.stderr)
json.dump(phd_off, open(os.path.join(SCRATCH, "phd_off.json"), "w"), ensure_ascii=False, indent=1)

# --- repeats + already-applied --------------------------------------------
# 8 Sep 2026: an applied company used to lose every posting forever. That threw away 87
# candidates in one run, Almetra's five new roles among them. Now a candidate is dropped only
# when the log holds the same role at that company; otherwise it is kept and tagged
# `applied_before` with the log row, and instructions/PROFILE.md tells the agent how to weigh it.
from jobid import same_title, same_company, norm_url, sent_match
POOL_URLS = {norm_url(c.get("url")) for c in cands if c.get("url")}


import decisions
SENT_PRINTS = decisions.sent_prints(ROOT)
fresh, repeats, applied_hits = [], [], []
for j in cands:
    if APPLIED_RE.search(j["company"] or ""):
        hit = [r for r in APPLIED_ROLES
               if same_company(r[0], j["company"] or "") and same_title(r[1], j["title"] or "")]
        if hit:
            applied_hits.append(j)
            continue
        j["applied_before"] = "; ".join("%s (%s, %s)" % (r[1], r[0], r[2]) for r in APPLIED_ROLES
                                         if same_company(r[0], j["company"] or ""))[:200] or "older list"
    # One recipe for every memory (jobid.sent_match): the seen entries, the pool links, the sent texts.
    m, so = sent_match(j["company"], j["title"], j.get("location", ""), j.get("url", ""), j.get("desc", ""),
                       seen, POOL_URLS, SENT_PRINTS)
    if so:
        # The sent job's own link is still in this pool and this row is a different link on the
        # same site, so both are open at once: a second opening, not a repeat (review, 29 Sep 2026:
        # Quantum-Systems Robotics & ML vs ML Engineer, Preply AI Learning vs AI Marketplace).
        j["similar_to_sent"] = "%s | %s (sent %s)" % (m.get("company", ""), m.get("title", ""), m.get("sent", ""))
        m = None
    if m:
        repeats.append((j, m))
        continue
    j["id"] = canonical_id(j["company"], j["title"], j.get("location", ""))
    fresh.append(j)

# 29 Sep 2026: jobs an earlier run read and dropped on a quoted German or clearance line,
# within the last 14 days. See scripts/rejected.py for why judgement rejections are not here.
import datetime
import rejected as rejmem
fresh, rej_before = rejmem.split(fresh, rejmem.load(), datetime.date.today().isoformat())

# 2 Oct 2026: every job a run read is remembered with its verdict (scripts/decisions.py), in every
# slot. A candidate read in the last 14 days leaves the list here, unless its text changed since or it
# is a second opening beside the remembered job. 73% of the reads of 1 and 2 Oct were such repeats.
fresh, remembered = decisions.split(fresh, decisions.load(ROOT), datetime.date.today().isoformat(), POOL_URLS)
json.dump([{"job": a["company"] + " | " + a["title"], "url": a.get("url"), "verdict": b.get("verdict"), "fit": b.get("fit"),
            "gate": b.get("gate"), "reason": b.get("reason"), "read": "%s %s" % (b.get("date"), b.get("slot"))}
           for a, b in remembered], open(os.path.join(SCRATCH, "remembered.json"), "w"), ensure_ascii=False, indent=1)
print("read by an earlier run, verdict remembered: %d skipped (remembered.json), %d back in the list because the text changed"
      % (len(remembered), sum(1 for j in fresh if j.get("text_changed"))), file=sys.stderr)

# 29 Sep 2026: the noon run reads what the morning left. Everything the morning read in full, sent
# or rejected, is skipped, so its reading budget goes further down the list. Only at noon: the
# evening keeps re-reading, because a run sometimes reverses a same-day rejection and he applied
# to some of those. RADAR_SKIP_READ_TODAY=1 forces it for a test.
from slots import now_slot
read_today = []
if now_slot() == "noon" or os.environ.get("RADAR_SKIP_READ_TODAY"):
    import glob as _glob
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    pool_read = []
    for mdp in _glob.glob(os.path.join(ROOT, "shortlists", today + "-morning.md")):
        pool_read += [dict(company=r["company"], title=r["title"]) for r in rejmem.parse_md(mdp)]
        try:
            js = json.load(open(mdp[:-3] + ".json", encoding="utf-8"))
            pool_read += [dict(company=j.get("company", ""), title=j.get("title", ""), url=j.get("apply_url", ""))
                          for j in (js.get("jobs") or []) if isinstance(j, dict)]
        except Exception:
            pass
    if pool_read:
        kept_r = []
        for j in fresh:
            (read_today.append(j) if is_repeat(j["company"], j["title"], "", pool_read, j.get("url", "")) else kept_r.append(j))
        fresh = kept_r
print("read earlier today (noon run only): %d skipped" % len(read_today), file=sys.stderr)

# 29 Sep 2026: rows that already carry the description (XING, ATS, arbeitnow, StepStone) and
# state a strong German requirement in one unsoftened sentence are dropped unread. About 20
# roles a run died on the language line after a full read. `hard_drop` flagged 0 of the 312
# sent packs wrongly and catches 94% of the German lines quoted in past rejections; the rest
# are still read. LinkedIn and BA rows have no description here and are unaffected.
# 2 Oct 2026: only a certain German requirement drops a row here (`lang_band.german`, verdict
# "drop"). An unclear line stays in the list with the sentences attached as `german_decide`, and
# the agent must quote one in `lang_line` and decide; final_check.py refuses the send otherwise.
from lang_band import german
german_off, kept, _gseen, german_marked = [], [], set(), 0
for j in fresh:
    verdict, lines = german(j.get("desc") or "") if j.get("desc") and not j.get("referral") else ("ok", [])
    if verdict != "drop":
        if verdict == "decide":
            j["german_decide"] = lines[:3]
            german_marked += 1
        kept.append(j)
    elif j["id"] not in _gseen:          # one job listed by several sources counts once (review)
        _gseen.add(j["id"])
        german_off.append((j, lines[0]))
fresh = kept

# 2 Oct 2026 (docs/PROBLEMS.md 3.6): the same split for nationality and security clearance
# (scripts/clearance.py). A citizenship requirement or a firm clearance requirement drops the row
# unread. A conditional line ("may need to be eligible") stays on the row as `clearance_flag`, and
# write_pack.py puts the sentence into the job's Gaps line. Referral rows are never dropped.
import clearance
clearance_off, kept = [], []
for j in fresh:
    verdict, lines = clearance.check(j.get("desc") or "") if j.get("desc") and not j.get("referral") else ("ok", [])
    if verdict == "drop":
        clearance_off.append((j, lines[0]))
        continue
    if verdict == "flag":
        j["clearance_flag"] = lines[:2]
    kept.append(j)
fresh = kept

# dedupe within this run
byid, uniq = {}, []
for j in fresh:
    m = is_repeat(j["company"], j["title"], j.get("location", ""),
                  [dict(company=u["company"], title=u["title"],
                        location=u.get("location", ""), id=u["id"],
                        url=u.get("url", "")) for u in uniq], j.get("url", ""))
    if m:
        continue
    uniq.append(j)

print("after repeat check: %d fresh (%d repeats skipped, %d already-applied co.)"
      % (len(uniq), len(repeats), len(applied_hits)), file=sys.stderr)
print("German required, dropped unread: %d (german_off.json)" % len(german_off), file=sys.stderr)
print("German line unclear, kept for the agent to decide: %d (`german_decide` on the row)" % german_marked, file=sys.stderr)
print("Nationality or clearance required, dropped unread: %d (clearance_off.json)" % len(clearance_off), file=sys.stderr)
json.dump([{"job": a["company"] + " | " + a["title"], "source": a.get("source"), "url": a.get("url"), "line": l}
           for a, l in clearance_off], open(os.path.join(SCRATCH, "clearance_off.json"), "w"), ensure_ascii=False, indent=1)
json.dump([{"job": a["company"] + " | " + a["title"], "source": a.get("source"), "url": a.get("url"), "line": l}
           for a, l in german_off], open(os.path.join(SCRATCH, "german_off.json"), "w"), ensure_ascii=False, indent=1)
print("rejected before on German or clearance, last %d days: %d skipped (rejected_before.json)"
      % (rejmem.DAYS, len(rej_before)), file=sys.stderr)
json.dump([{"job": a["company"] + " | " + a["title"], "matched": b["company"] + " | " + b["title"],
            "last": b.get("last"), "reason": b.get("reason")} for a, b in rej_before],
          open(os.path.join(SCRATCH, "rejected_before.json"), "w"), ensure_ascii=False, indent=1)

# 29 Sep 2026: read order. Every row gets a cheap score from title, description and date
# (scripts/prescore.py) and the file is sorted by it, best first. Nothing is dropped here.
import prescore
# 29 Sep 2026: titles that can never be his job, dropped before anything reads them. Only when the
# title also carries no AI, KI, ML or data word: "Senior Machine Learning Engineer - Radiologie-KI"
# stays. Tested that day: of the 404 rows the morning run left unread, this caught 46 of the 136 an
# agent's title triage dropped, and none of the rows it kept, none of the 34 useful ones, and none
# of the 710 sent or 181 applied titles. The rest is the agent's own title triage (scripts/triage.py).
TITLE_NOISE_DROP = cfg.rx("filters", "title_noise_drop")
TITLE_FIELD = cfg.rx("filters", "title_field")
title_noise = [j for j in uniq if TITLE_NOISE_DROP.search(j.get("title") or "") and not TITLE_FIELD.search(j.get("title") or "")]
uniq = [j for j in uniq if j not in title_noise]
json.dump([{"job": j["company"] + " | " + j["title"], "source": j.get("source")} for j in title_noise],
          open(os.path.join(SCRATCH, "title_noise.json"), "w"), ensure_ascii=False, indent=1)
print("title noise dropped: %d (title_noise.json)" % len(title_noise), file=sys.stderr)

# 29 Sep 2026: benefits sections and diversity boilerplate cut from the descriptions the run reads
# (scripts/trim_desc.py). Every check that reads the description has already run above.
from trim_desc import trim
for j in uniq:
    if j.get("desc"):
        j["desc"], j["desc_cut"] = trim(j["desc"])
print("descriptions trimmed: %d characters of benefits and boilerplate cut from %d rows"
      % (sum(j.get("desc_cut", 0) for j in uniq), sum(1 for j in uniq if j.get("desc_cut"))), file=sys.stderr)
uniq = prescore.order(uniq)
json.dump(uniq, open(os.path.join(SCRATCH, "candidates.json"), "w"),
          ensure_ascii=False, indent=1)
json.dump([{"job": a["company"] + " | " + a["title"], "matched": b["company"] + " | " + b["title"]}
           for a, b in repeats], open(os.path.join(SCRATCH, "repeats.json"), "w"),
          ensure_ascii=False, indent=1)

print("recruiter-tagged: %d   referral-tagged: %d"
      % (sum(1 for j in uniq if j.get("recruiter")), sum(1 for j in uniq if j.get("referral"))),
      file=sys.stderr)
for j in uniq:
    print("%3d %-26s | %-62s | %-26s | %-12s | %s%s" % (j.get("prescore", 0), j["company"][:26], j["title"][:62],
                                          (j.get("location") or "")[:26], j["source"][:12],
                                          (j.get("date") or "")[:10],
                                          ("  [REFERRAL]" if j.get("referral") else "")
                                          + ("  [recruiter]" if j.get("recruiter") else "")
                                          + ("  [applied before: %s]" % j["applied_before"] if j.get("applied_before") else "")))
