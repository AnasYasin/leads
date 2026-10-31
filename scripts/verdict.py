#!/usr/bin/env python3
"""Verdicts for the jobs scripts/read_next.py printed, and the shortlist draft built from them.

Added 2 Oct 2026 (docs/PROBLEMS.md 2.2, 4.4, 4.5, 6.2). A verdict is written right after a job is read,
while its text is in front of the agent, and it is on disk before the next batch arrives. So a full
context cannot lose it, a run cannot claim a read it did not do, and nobody writes 160 reasons from
memory at the end (25 minutes on 2 Oct morning).

    python3 scripts/verdict.py $SC - <<'EOF'       hand in the verdicts for the last batch (a JSON list on
    [...]                                          stdin, or a file path in place of "-"), then print
    EOF                                            the next batch
    python3 scripts/verdict.py $SC --draft         write $SC/shortlist.json from all verdicts
    python3 scripts/verdict.py $SC --show          every verdict so far, one line each

v.json is a list, one object per job:
    {"id": "<id from the reader>", "fit": 7, "gate": "", "band": "A",
     "lang_line": "<the sentence from the text, or: no language line in the posting>",
     "reason": "<one line tied to his real work, or the quoted line the gate rests on>"}

What the code makes of fit and gate (instructions/PROFILE.md, and the candidate's decision of 2 Oct 2026 on the cap):
    a gate                     reject      never reaches him; listed under Rejected with the reason
    no gate, fit 7 or higher   send        sent in full, no cap on how many
    no gate, fit 6             also        one line under "Fit 6, one line each"
    no gate, fit 5 or lower    borderline  one line under "Borderline", he decides
    a referral row, fit 5+     send        (instructions/PROFILE.md)

`hard_req` (docs/PROBLEMS.md 4.3, the candidate 2 Oct 2026). When the posting demands years of experience in a
specific tool or method he has never used, and the role is built on it, quote that requirement in
`hard_req`. The fit is then capped at 6, so the job is one line with the requirement shown, and he
decides. It is not a gate: a missing skill never rejects a job. Every verdict at fit 7 or higher
must say `hard_req`, either the quoted line or "none", so the question is answered and not skipped.
On 30 Sep the radar sent zooplus (3+ years LP/MIP and Gurobi), Skaylink (Copilot Studio) and
Delivery Hero (production DCN-V2 and MMoE ranking) in full, and he removed all three by hand.

Checks. A verdict is refused, with the reason, when the job was not printed by the reader, when the
gate is not one of the ten, when `lang_line` does not quote the text although the text names German,
or when the row carries an unclear German line (`german_decide`) and `lang_line` does not quote it.
"""
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import read_next as R  # noqa: E402
from lang_band import _LANG, german  # noqa: E402
import clearance  # noqa: E402

GATES = {"german", "clearance", "years", "phd", "non_software", "lead", "field", "closed", "repeat", "unpaid", "no_text"}
NO_LINE = "no language line in the posting"
SEND_FIT, ALSO_FIT, REFERRAL_FIT = 7, 6, 5
HARD_CAP = 6          # the highest fit a job with a `hard_req` can have


def _norm(t):
    return re.sub(r"[^0-9a-zà-ÿ]+", "", (t or "").lower())


def quotes(line, text):
    """True when `line` carries at least 25 letters in a row of `text`."""
    a, b = _norm(line), _norm(text)
    if len(a) < 12:
        return False
    return any(a[i:i + 25] in b for i in range(0, max(1, len(a) - 24), 3)) if len(a) >= 25 else a in b


def kind(v, row):
    if v.get("gate"):
        return "reject"
    fit = v["fit"]
    if fit >= SEND_FIT or (row.get("referral") and fit >= REFERRAL_FIT):
        return "send"
    return "also" if fit >= ALSO_FIT else "borderline"


def check(v, rows, printed):
    """(clean verdict, None) or (None, why it is refused)."""
    if not isinstance(v, dict) or not v.get("id"):
        return None, "no id"
    i = str(v["id"]).strip()
    if i not in rows:
        return None, "%s: not in candidates.json" % i
    row = rows[i]
    text = row.get("desc") or ""
    reason = " ".join(str(v.get("reason") or "").split())
    if str(v.get("gate") or "").strip().lower() == "no_text":
        # 29 Oct 2026: a row no link and no web search could resolve. Retired without a read, and
        # remembered like any verdict, so it stops coming back under "Could not be read".
        if text.strip():
            return None, "%s: the job has text. Read it with read_next.py and give a real verdict." % i
        if len(reason) < 15:
            return None, "%s: reason is missing. Say where you searched and what the pages said." % i
        # 30 Oct 2026: `verdict` was missing here and `--draft` crashed in lists() on the first noon run.
        return dict(id=i, fit=0, gate="no_text", band="", lang_line="", reason=reason[:400], hard_req="",
                    company=row.get("company") or "", title=row.get("title") or "", verdict="reject"), None
    if i not in printed:
        return None, "%s: the reader has not printed this job. Read it with read_next.py first." % i
    try:
        fit = int(round(float(v.get("fit"))))
    except (TypeError, ValueError):
        return None, "%s: fit must be a number from 0 to 10" % i
    if not 0 <= fit <= 10:
        return None, "%s: fit must be a number from 0 to 10" % i
    gate = str(v.get("gate") or "").strip().lower()
    if gate and gate not in GATES:
        return None, "%s: gate '%s' is not one of %s. Software skills are never a gate; leave it empty and score the fit." % (
            i, gate, ", ".join(sorted(GATES)))
    if len(reason) < 15:
        return None, "%s: reason is missing. One plain line." % i
    band = str(v.get("band") or "").strip().upper()
    if not gate and band not in ("A", "B"):
        return None, "%s: band must be A or B (instructions/PROFILE.md, Language rule)" % i
    line = " ".join(str(v.get("lang_line") or "").split())
    verdict, lines = ("ok", []) if row.get("referral") else german(text)
    names_german = any(m.lastgroup == "de" for m in _LANG.finditer(text))
    cv, clines = ("ok", []) if row.get("referral") else clearance.check(text)
    if not gate and cv == "drop":
        return None, "%s: the text requires a nationality or a security clearance: '%s'. Reject it with gate clearance." % (i, clines[0][:180])
    if gate == "german":
        if not quotes(line, text) and not quotes(reason, text):
            return None, "%s: gate german needs the sentence from the text, quoted in lang_line" % i
    elif not gate:
        if verdict == "drop":
            return None, "%s: the text states a German level he does not have: '%s'. Reject it with gate german." % (i, lines[0][:160])
        if verdict == "decide" and not any(quotes(line, l) for l in lines):
            return None, "%s: unclear German line. Quote it in lang_line and decide: '%s'" % (i, lines[0][:200])
        if names_german and not quotes(line, text):
            return None, "%s: the text names German. lang_line must quote that sentence from the text." % i
        if not line:
            line = NO_LINE
    hard = " ".join(str(v.get("hard_req") or "").split())
    if hard.lower() in ("none", "no", "-", "n/a"):
        hard = ""
    if not gate:
        if fit >= SEND_FIT and "hard_req" not in v:
            return None, ("%s: fit %d sends this job in full. Say hard_req: quote the requirement that demands years in a tool or "
                          "method he has never used, or write \"none\"." % (i, fit))
        if hard and not quotes(hard, text):
            return None, "%s: hard_req must quote the requirement from the text" % i
        if hard and fit > HARD_CAP:
            fit = HARD_CAP
    out = dict(id=i, fit=fit, gate=gate, band=band if band in ("A", "B") else "", lang_line=line[:400], reason=reason[:400],
               hard_req=hard[:300] if not gate else "", company=row.get("company") or "", title=row.get("title") or "")
    out["verdict"] = kind(out, row)
    return out, None


def hand_in(sc, path):
    try:
        data = json.load(sys.stdin if path == "-" else open(path, encoding="utf-8"))
    except (OSError, ValueError) as ex:
        print("could not read the verdicts (%s): %s. Nothing was stored. Send a JSON list." % (path, str(ex)[:120]))
        return 1
    if isinstance(data, dict):
        data = data.get("verdicts") if isinstance(data.get("verdicts"), list) else [data]
    rows = {R.cid(j): j for j in R.candidates(sc)}
    printed = R.log(sc)["printed"]
    vd = R.verdicts(sc)
    bad = []
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    for v in data:
        clean, why = check(v, rows, printed)
        if why:
            bad.append(why)
        else:
            clean["at"] = now
            vd[clean["id"]] = clean
    json.dump(vd, open(os.path.join(sc, "verdicts.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = len(data) - len(bad)
    for w in bad:
        print("REFUSED  " + w)
    wait = R.pending(sc)
    print("%d verdicts stored, %d refused. %s" % (ok, len(bad),
          ("Still without a verdict in the last batch: " + ", ".join(wait)) if wait else "The batch is complete."))
    if bad or wait:
        return 1
    # The next batch follows at once, so a batch costs one command.
    if "--no-next" in sys.argv:
        return 0
    return R.main(["read_next.py", sc] + (["--more"] if "--more" in sys.argv else []))


def _flag(j):
    """The conditional clearance sentences of a row, from its text (rows added by hand carry no mark)."""
    v, lines = ("ok", []) if j.get("referral") else clearance.check(j.get("desc") or "")
    return lines if v == "flag" else []


def _size(company):
    """staff, size_class and staff_source from the company cache, empty when the cache has none."""
    try:
        import company_cache
        d = company_cache.get(company) or {}
    except Exception:
        d = {}
    if d.get("staff"):
        return dict(staff=d["staff"], size_class=d.get("size_class", ""),
                    staff_source="company cache, %s" % (d.get("staff_source") or d.get("updated", "")))
    return dict(staff="", size_class="", staff_source="")


def lists(sc):
    """jobs, also_found, borderline and rejected, built from the verdicts."""
    rows = {R.cid(j): j for j in R.candidates(sc)}
    out = dict(jobs=[], also_found=[], borderline=[], rejected=[])
    for i, v in R.verdicts(sc).items():
        j = rows.get(i) or {}
        link = j.get("apply_url") or j.get("url") or ""
        if v["verdict"] == "send":
            src = j.get("source") or ""
            out["jobs"].append(dict(
                id=i, company=v["company"], title=v["title"], location=j.get("location", ""), employment=j.get("employment", ""),
                posted=(j.get("date") or "")[:10], source=src, tier=1, fit=v["fit"], priority=v["fit"], band=v["band"],
                lang_line=v["lang_line"], referral=bool(j.get("referral")), recruiter=bool(j.get("recruiter")), contact="",
                salary=j.get("salary") or "", why=v["reason"], company_note="", bonus=0, **_size(v["company"]),
                gaps=" ".join(x for x in [("Hard requirement he cannot back: '%s'." % v["hard_req"]) if v.get("hard_req") else "",
                                          clearance.gap_text(j.get("clearance_flag") or _flag(j))] if x),
                apply_url=link, employer_site=j.get("employer_site", ""), fallback_url="" if link == j.get("url") else (j.get("url") or ""),
                linkedin_url=j.get("url", "") if src == "linkedin" else "", xing_url=j.get("url", "") if src == "xing" else "",
                ba_url=j.get("url", "") if src == "Bundesagentur" else "", cv_base="", desc=j.get("desc") or ""))
        elif v["verdict"] == "also":
            out["also_found"].append(dict(company=v["company"], title=v["title"], location=j.get("location", ""), fit=v["fit"],
                                          band=v["band"], url=link,
                                          note=("NEEDS: '%s'. %s" % (v["hard_req"], v["reason"])) if v.get("hard_req") else v["reason"]))
        elif v["verdict"] == "borderline":
            out["borderline"].append(dict(company=v["company"], title=v["title"], fit=v["fit"], url=link, reason=v["reason"]))
        else:
            quoted = v["gate"] == "german" and v["lang_line"] and v["lang_line"] != NO_LINE and v["lang_line"] not in v["reason"]
            out["rejected"].append(dict(company=v["company"], title=v["title"], fit=v["fit"], gate=v["gate"],
                                        reason="%s '%s'" % (v["reason"], v["lang_line"]) if quoted else v["reason"]))
    for k in ("jobs", "also_found", "borderline"):
        out[k].sort(key=lambda r: -(r.get("fit") or 0))
    return out


def draft(sc):
    """The shortlist skeleton from the verdicts. The agent fills in what only it knows."""
    slot = R._load(os.path.join(sc, "run_slot.json"), {})
    sl = dict(date=slot.get("date", ""), slot=slot.get("slot", ""), intro="", direct_look=[], coverage=[], notes="")
    sl.update(lists(sc))
    sl.update(counts(sc))
    out = os.path.join(sc, "shortlist.json")
    if os.path.exists(out):
        out = os.path.join(sc, "shortlist_draft.json")
    json.dump(sl, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("%s written: %d to send (fit %d or higher), %d at fit %d, %d borderline, %d rejected."
          % (out, len(sl["jobs"]), SEND_FIT, len(sl["also_found"]), ALSO_FIT, len(sl["borderline"]), len(sl["rejected"])))
    print("Fill in for each job to send: apply_url (the employer's own posting), priority, why, gaps, company_note, "
          "size_class, staff, cv_base. Then intro, coverage and notes. Do not touch desc, rejected, borderline or also_found: "
          "write_pack.py takes those from verdicts.json.")
    return 0


def counts(sc):
    """The reading numbers, from the reader's log and nothing else."""
    rows = R.candidates(sc)
    vd, printed = R.verdicts(sc), R.log(sc)["printed"]
    read = [j for j in rows if R.cid(j) in vd and R.cid(j) in printed]
    unread = [j for j in rows if R.cid(j) not in vd]
    by = {}
    for j in unread:
        s = j.get("source") or "?"
        s = "ats" if s.startswith("ATS/") else "getro" if s.startswith("getro") else s
        by[s] = by.get(s, 0) + 1
    return dict(candidates=len(rows), read_full=len(read), left_unread=len(unread), unread_by_source=by,
                no_text=sum(1 for j in unread if not R.has_text(j)),
                remembered=len(R._load(os.path.join(sc, "remembered.json"), [])))


NO_READER = ("this run never started scripts/read_next.py, so nothing was read. Read the candidates with "
             "python3 scripts/read_next.py <scratch> and hand in the verdicts with scripts/verdict.py")


def no_reader(sc):
    """True for a real run that has candidates and never started the reader (3 Oct 2026).

    collect_all.py writes run_slot.json, so its presence marks a real run. A laptop backfill has
    none and stays unchecked. read_next.py creates read_log.json on its first call, even when it
    prints nothing because the time is up, so a missing log means the reader was never used."""
    return (os.path.exists(os.path.join(sc, "run_slot.json"))
            and not os.path.exists(os.path.join(sc, "read_log.json"))
            and len(R.candidates(sc)) > 0)


def reading_record(sc):
    """What the reader printed and when the verdicts came back, one entry per batch. Stored with
    the shortlist so a run can be audited after its scratch directory is gone (scripts/read_audit.py)."""
    lg, vd = R.log(sc), R.verdicts(sc)
    out = []
    for b in lg["batches"]:
        ids = b.get("ids") or []
        ats = sorted(vd[i]["at"] for i in ids if i in vd and vd[i].get("at"))
        out.append(dict(n=b.get("n"), printed_at=b.get("at") or "", jobs=len(ids),
                        chars=sum(lg["printed"].get(i, 0) for i in ids),
                        verdicts=sum(1 for i in ids if i in vd), verdicts_at=ats[-1] if ats else ""))
    return out


def unread_jobs(sc, jobs):
    """The jobs of a shortlist that the reader did not print in full, as (job, why). Empty when the
    render is a laptop backfill (no run_slot.json and no reader log)."""
    if no_reader(sc):
        return [(j, NO_READER) for j in jobs]
    if not os.path.exists(os.path.join(sc, "read_log.json")):
        return []
    from jobid import is_repeat
    rows = R.candidates(sc)
    by_id = {R.cid(j): j for j in rows}
    vd, printed = R.verdicts(sc), R.log(sc)["printed"]
    out = []
    for j in jobs:
        i = j.get("id") if j.get("id") in by_id else None
        if i is None:
            m = is_repeat(j.get("company") or "", j.get("title") or "", j.get("location", ""), rows,
                          j.get("apply_url") or j.get("url") or "")
            i = R.cid(m) if m else None
        if i is None:
            out.append((j, "not in the candidate list. Add it with read_next.py --add <url> \"<company>\" \"<title>\" and read it."))
        elif not R.has_text(by_id[i]):
            out.append((j, "it has no text. A job nobody read is not sent."))
        elif i not in printed:
            out.append((j, "the reader never printed it"))
        elif i not in vd:
            out.append((j, "it has no verdict"))
        elif vd[i]["verdict"] != "send":
            out.append((j, "its verdict is '%s' (fit %s%s), not send" % (vd[i]["verdict"], vd[i]["fit"],
                                                                         ", gate " + vd[i]["gate"] if vd[i]["gate"] else "")))
        else:
            j.setdefault("id", i)
    return out


if __name__ == "__main__":
    sc = sys.argv[1]
    if "--draft" in sys.argv:
        sys.exit(draft(sc))
    if "--show" in sys.argv:
        for i, v in R.verdicts(sc).items():
            print("%-10s fit %-2s %-12s %s | %s · %s" % (v["verdict"], v["fit"], v["gate"] or "-", v["company"][:30], v["title"][:50], v["reason"][:90]))
        print(counts(sc))
        sys.exit(0)
    sys.exit(hand_in(sc, sys.argv[2]))
