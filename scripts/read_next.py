#!/usr/bin/env python3
"""The reader. Prints the next unread jobs in full and keeps a log of what it printed.

Added 2 Oct 2026 (docs/PROBLEMS.md group 2). Until then every run wrote its own helper and printed part
of each job: 1,900 to 2,800 characters at the top of the list, 300 to 800 further down, against a
median posting of 4,400. Runs then reported "read in full". On 30 Sep the noon run claimed 248 jobs
read in 13 minutes, and about 110 of them had been shown at about 300 characters.

    python3 scripts/read_next.py $SC

prints one batch: a few jobs, each with its whole text and, above the text, the lines that decide a
job most often (language, clearance or nationality, years of experience, PhD). After the batch,
hand in a verdict for every job in it:

    python3 scripts/verdict.py $SC - <<'EOF'
    [ ... one verdict per job ... ]
    EOF

verdict.py stores them and prints the next batch itself, so one command per batch is enough. This
script refuses to print a new batch while a job of the last one has no verdict, so every decision is made while the text is still in front of you, and is
on disk before the next text arrives.

What it enforces:
  - a job counts as read only when this script printed all of it (read_log.json). write_pack.py
    takes `read_full` from that log, and final_check.py refuses to send a job that is not in it;
  - a job with no text is never printed and never counts as read. It is listed at the end with the
    reason from no_text.json;
  - reading stops at `reading.stop_minutes` after collection started (--more goes on anyway).

A batch is at most `reading.batch_chars` characters, so the output fits in one tool result. Each
batch is also saved as $SC/batches/batch_<n>.txt, in case the output was shortened on the way.

    python3 scripts/read_next.py $SC --again            print the last batch again
    python3 scripts/read_next.py $SC --status           counts only
    python3 scripts/read_next.py $SC --add <url> "<company>" "<title>"
                                                        a job found outside the candidate list (a careers
                                                        page, the funded-startup sweep): fetch it, add it
                                                        to candidates.json, and print it like any other
"""
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cfg  # noqa: E402
from jobid import canonical_id  # noqa: E402
from lang_band import german  # noqa: E402
import clearance  # noqa: E402
from slots import elapsed_minutes  # noqa: E402

THIN = 300      # the same bar as fetch_desc.py: shorter than this is not a posting

KEY = [
    ("language", re.compile(r"deutsch(?!land)|german(?!y)|englisch|english|sprachkenntnis|sprachniveau|verhandlungssicher"
                            r"|working language|arbeitssprache|languages?:|flie(?:ß|ss)end|fluen[tc]|\b[abc][12]\b|muttersprach"
                            r"|native speaker", re.I)),
    ("clearance or nationality", re.compile(
        r"security clearance|sicherheits(?:ü|ue)berpr|\bs(?:ü|ue)g\b|\bü[123]\b|clearance|nationality|staatsangeh|staatsb(?:ü|ue)rger"
        r"|citizen|\bnato\b|eu[- ]b(?:ü|ue)rger|work permit|arbeitserlaubnis|export control|exportkontroll|\bitar\b|geheimschutz", re.I)),
    ("years", re.compile(r"\b\d{1,2}\s*\+?\s*(?:(?:-|–|to|bis)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs|jahre[n]?)\b|mehrj(?:ä|ae)hrig|langj(?:ä|ae)hrig", re.I)),
    ("phd", re.compile(r"\bph\.?\s?d\b|promotion\b|promoviert|doktor|doctorate|publications?\b|publikation", re.I)),
]


def conf(name, default):
    try:
        return cfg.get("reading", name)
    except Exception:
        return default


def _load(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def cid(j):
    return j.get("id") or canonical_id(j.get("company") or "", j.get("title") or "", j.get("location", ""))


def candidates(sc):
    return _load(os.path.join(sc, "candidates.json"), [])


def log(sc):
    d = _load(os.path.join(sc, "read_log.json"), {})
    d.setdefault("batches", [])
    d.setdefault("printed", {})
    return d


def verdicts(sc):
    return _load(os.path.join(sc, "verdicts.json"), {})


def has_text(j):
    return len(j.get("desc") or "") >= THIN


def key_lines(text):
    """{label: [sentence, ...]} for the lines that decide a job most often."""
    out = {}
    pieces = [p.strip() for p in re.split(r"\n|(?<=[.!?])\s+", text or "") if p.strip()]
    for label, rx in KEY:
        hits = list(dict.fromkeys(p[:300] for p in pieces if rx.search(p) and len(p) < 600))
        if hits:
            out[label] = hits[:8]
    return out


def block(j, k, total):
    """One job, whole."""
    text = j.get("desc") or ""
    out = ["=" * 100, "[%d of %d]  id: %s" % (k, total, cid(j)), "%s | %s" % (j.get("company"), j.get("title")),
           "%s · posted %s · %s · prescore %s" % (j.get("location") or "no location", (j.get("date") or "no date")[:10],
                                                 j.get("source"), j.get("prescore", "?"))]
    out.append("url: %s" % (j.get("url") or "none"))
    for k2, label in (("apply_url", "apply_url"), ("employer_site", "employer_site"), ("externe_url", "externe_url"),
                      ("salary", "salary from the source"), ("employment", "employment")):
        if j.get(k2):
            out.append("%s: %s" % (label, j[k2]))
    flags = [f for f in ("REFERRAL, send at fit 5 or higher" if j.get("referral") else "",
                         "recruiter posting" if j.get("recruiter") else "",
                         "applied before: %s" % j["applied_before"] if j.get("applied_before") else "",
                         "similar to a sent job: %s" % j["similar_to_sent"] if j.get("similar_to_sent") else "",
                         "TEXT CHANGED: %s" % j["text_changed"] if j.get("text_changed") else "") if f]
    if flags:
        out.append("flags: " + " · ".join(flags))
    v, lines = ("ok", []) if j.get("referral") else german(text)
    if v == "decide":
        out.append("GERMAN LINE TO DECIDE. Read it in the text, then reject with gate german or keep and quote it in lang_line:")
        out += ["   > " + l for l in lines]
    elif v == "drop":
        out.append("GERMAN: certain requirement, reject with gate german:")
        out += ["   > " + l for l in lines[:2]]
    cv, clines = ("ok", []) if j.get("referral") else clearance.check(text)
    if cv == "drop":
        out.append("NATIONALITY OR CLEARANCE: required, reject with gate clearance:")
        out += ["   > " + l for l in clines[:2]]
    elif cv == "flag":
        out.append("CLEARANCE, CONDITIONAL. Not a reason to reject. The code puts this sentence into the Gaps line:")
        out += ["   > " + l for l in clines[:2]]
    kl = key_lines(text)
    if kl:
        out.append("KEY LINES (pulled out by the code, all of them are also in the text below)")
        for label, hits in kl.items():
            out += ["   %s: %s" % (label, h) for h in hits]
    else:
        out.append("KEY LINES: none found. No language, clearance, years or PhD line in this text.")
    out.append("FULL TEXT, %d characters, %d words" % (len(text), len(text.split())))
    out.append(text)
    return "\n".join(out)


def pending(sc):
    """Ids of the last batch that still have no verdict."""
    lg, vd = log(sc), verdicts(sc)
    last = lg["batches"][-1]["ids"] if lg["batches"] else []
    return [i for i in last if i not in vd]


def status(sc):
    rows, lg, vd = candidates(sc), log(sc), verdicts(sc)
    no_text = [j for j in rows if not has_text(j)]
    todo = [j for j in rows if has_text(j) and cid(j) not in vd]
    return dict(candidates=len(rows), read=sum(1 for j in rows if cid(j) in vd and cid(j) in lg["printed"]),
                unread=len(todo), no_text=len(no_text), batches=len(lg["batches"]))


def next_batch(sc):
    rows, vd = candidates(sc), verdicts(sc)
    limit, most = int(conf("batch_chars", 20000)), int(conf("batch_jobs", 6))
    todo = [j for j in rows if has_text(j) and cid(j) not in vd]
    batch, size = [], 0
    for j in todo:
        n = len(j.get("desc") or "") + 900
        if batch and (size + n > limit or len(batch) >= most):
            break
        batch.append(j)
        size += n
    return batch, len(todo)


def print_batch(sc, batch, left, again=False):
    lg = log(sc)
    st = status(sc)
    done = st["read"]
    total = done + left
    n = len(lg["batches"]) + (0 if again else 1)
    parts = [block(j, done + i + 1, total) for i, j in enumerate(batch)]
    mins = elapsed_minutes(sc)
    foot = ["=" * 100,
            "Batch %d: %d jobs printed in full. %d more unread after this batch, %d without text.%s"
            % (n, len(batch), left - len(batch), st["no_text"], "" if mins is None else " %d minutes since collection started." % mins),
            "Now hand in one verdict per job above. This one command stores them and prints the next batch:",
            "    python3 scripts/verdict.py %s - <<'EOF'" % sc,
            '    [{"id": "<id above>", "fit": 0-10, "gate": "" or one of german|clearance|years|phd|non_software|lead|field|closed|repeat|unpaid (no_text only for a row the reader cannot print, see retext.py),',
            '      "band": "A" or "B", "lang_line": "<the sentence from the text, or: no language line in the posting>", "reason": "<one line>",',
            '      "hard_req": "<the quoted requirement that demands years in a tool or method he has never used, or: none>"}, ...]',
            "    EOF",
            "Ids: " + ", ".join(cid(j) for j in batch)]
    text = "\n".join(parts + foot)
    os.makedirs(os.path.join(sc, "batches"), exist_ok=True)
    open(os.path.join(sc, "batches", "batch_%d.txt" % n), "w", encoding="utf-8").write(text)
    if not again:
        lg["batches"].append(dict(n=n, ids=[cid(j) for j in batch],
                                  at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")))
        for j in batch:
            lg["printed"][cid(j)] = len(j.get("desc") or "")
        json.dump(lg, open(os.path.join(sc, "read_log.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(text)
    if len(text) > int(conf("batch_chars", 20000)) + 6000:
        print("This batch is long. If the output above was shortened, read %s" % os.path.join(sc, "batches", "batch_%d.txt" % n))


def add(sc, url, company, title):
    """A job from outside the candidate list. Fetched, added to candidates.json, read like the rest."""
    import jobpage
    rows = candidates(sc)
    r = jobpage.read(url, title)
    if not r.get("desc"):
        sys.exit("NOT ADDED, no text: %s" % r.get("error"))
    j = dict(source="web", company=company, title=title, location="", url=url, date="", desc=r["desc"],
             desc_src=r.get("desc_src"), desc_len=len(r["desc"]), added_by_hand=True)
    j["id"] = canonical_id(company, title, "")
    if any(cid(x) == j["id"] for x in rows):
        sys.exit("already in the candidate list: %s" % j["id"])
    rows.insert(0, j)
    json.dump(rows, open(os.path.join(sc, "candidates.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("added %s (%d characters, %s). It is first in the next batch." % (j["id"], len(j["desc"]), j["desc_src"]))


def started(sc):
    """Mark the run as one that used the reader. write_pack.py and final_check.py refuse a real run
    that has candidates and no reader log (3 Oct 2026): before, a render without a log was not
    checked at all, so a run that ignored the reader could still send."""
    p = os.path.join(sc, "read_log.json")
    if not os.path.exists(p):
        json.dump({"batches": [], "printed": {}}, open(p, "w", encoding="utf-8"))


def main(argv):
    sc = argv[1]
    started(sc)
    if "--status" in argv:
        s = status(sc)
        print("%(candidates)d candidates: %(read)d read in full with a verdict, %(unread)d unread, %(no_text)d without text, "
              "%(batches)d batches printed" % s)
        return 0
    if "--add" in argv:
        i = argv.index("--add")
        add(sc, argv[i + 1], argv[i + 2], argv[i + 3])
        return 0
    wait = pending(sc)
    if "--again" in argv:
        lg = log(sc)
        if not lg["batches"]:
            print("no batch printed yet")
            return 1
        ids = lg["batches"][-1]["ids"]
        rows = {cid(j): j for j in candidates(sc)}
        print_batch(sc, [rows[i] for i in ids if i in rows], next_batch(sc)[1], again=True)
        return 0
    if wait:
        print("NO NEW BATCH. %d jobs of the last batch have no verdict yet: %s" % (len(wait), ", ".join(wait)))
        print("Hand in a verdict for each (python3 scripts/verdict.py %s - <<'EOF' ... EOF), or print the batch again with --again." % sc)
        return 1
    mins, stop = elapsed_minutes(sc), int(conf("stop_minutes", 80))
    batch, left = next_batch(sc)
    if not batch:
        s = status(sc)
        print("ALL READ. %(read)d jobs read in full with a verdict, %(no_text)d without text (no_text.json), 0 unread." % s)
        print("Next: python3 scripts/verdict.py %s --draft" % sc)
        return 0
    if mins is not None and mins >= stop and "--more" not in argv:
        print("TIME. %d minutes since collection started, the reading limit is %d. %d jobs stay unread and go to the "
              "backlog. Next: python3 scripts/verdict.py %s --draft   (--more reads on anyway)" % (mins, stop, left, sc))
        return 2
    print_batch(sc, batch, left)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
