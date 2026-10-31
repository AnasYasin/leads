#!/usr/bin/env python3
"""Source and board health across runs, and the ranked candidate list of the last run.

Added 29 Sep 2026. Before this a source that quietly shrank, or a board that returned
nothing for a week, was only noticed when someone read the collector logs closely, and the
per-board report lived in the scratch folder and was gone after the run. collect_all.py now
calls this at the end of every collection:

    python3 scripts/health.py <scratch>              print flags, record the run
    python3 scripts/health.py <scratch> --dry        print flags, record nothing (laptop tests)
    python3 scripts/health.py --render               rebuild reports/HEALTH.md from state/health.json and shortlists/

state/health.json keeps the last 30 runs: rows per source, and per board the job count and error.
state/health_candidates.json is the last run's candidates.json in read order, trimmed to the fields
needed to see what a run left unread (a run reads from the top, so everything below its
`read_full` count was not read). write_pack.py prints the flags of the current run in the email.

Flags:
  SOURCE LOW   a source under half its average over the previous 5 runs (needs 3 runs of history)
  SOURCE ZERO  a source that returned no rows at all
  BOARD DEAD   a board with an error on this run and the two before it, again at 10, 20, 30 runs
  BOARD EMPTY  a board with 0 jobs and no error on this run and the two before it, same cadence
  BOARD NEW    first time a board is polled: its job count or its error
  FIRST RUN    no history yet: one line with the boards that failed
  TEXT EMPTY   more than 10% of a source's rows have under 300 characters of text (7 Oct 2026)

Text check, added 7 Oct 2026 after the candidate reported StepStone jobs reaching the run empty. Two points
are counted for StepStone, XING and LinkedIn and stored on the run as `text`:
  - collected: rows the collector wrote, and how many carry 300+ characters of description.
    StepStone and XING bring the text here. LinkedIn brings none by design, so it is not flagged here.
  - candidates: the same count over candidates.json after fetch_desc.py, which fetches the missing
    text. fetch_desc.py calls `record_text(sc)` at its end, so this part is filled in later in the run.
write_pack.py prints the counts in the email every run, flagged or not.
"""
import datetime, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "state/health.json")
CANDS = os.path.join(ROOT, "state/health_candidates.json")
SOURCES = ["ba", "ats", "getro", "talent", "arbeitnow", "linkedin", "xing", "stepstone"]
KEEP = 30
TEXT_SOURCES = ("stepstone", "xing", "linkedin")
TEXT_AT_COLLECTION = ("stepstone", "xing")      # LinkedIn rows get their text in fetch_desc.py
TEXT_MIN = 300                                   # the same bar as fetch_desc.THIN
TEXT_FLAG_SHARE = 0.10


def _load(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def _text_len(j):
    return max(j.get("desc_len") or 0, len(j.get("desc") or ""))


def text_stats(scratch):
    """{source: {rows, rows_text, cand, cand_text}} for StepStone, XING and LinkedIn.
    Only rows with a link count, so a stub row cannot pass as a job."""
    out = {}
    for s in TEXT_SOURCES:
        rows = _load(os.path.join(scratch, s + ".json"), None)
        if isinstance(rows, list):
            rows = [r for r in rows if isinstance(r, dict) and r.get("url")]
            out[s] = dict(rows=len(rows), rows_text=sum(1 for r in rows if _text_len(r) >= TEXT_MIN))
    cands = _load(os.path.join(scratch, "candidates.json"), [])
    cands = [j for j in cands if isinstance(j, dict)] if isinstance(cands, list) else []
    for s in TEXT_SOURCES:
        c = [j for j in cands if j.get("source") == s]
        if c or s in out:
            out.setdefault(s, {}).update(cand=len(c), cand_text=sum(1 for j in c if _text_len(j) >= TEXT_MIN))
    return out


def text_flags(stats, after_fetch):
    """TEXT EMPTY flags. Before the fetch only the collected rows of StepStone and XING are judged;
    after it, the candidates of all three sources."""
    flags = []
    for s, t in stats.items():
        if s in TEXT_AT_COLLECTION and t.get("rows"):
            empty = t["rows"] - t["rows_text"]
            if empty > TEXT_FLAG_SHARE * t["rows"]:
                flags.append("TEXT EMPTY %s %d of %d collected rows have under %d characters of text"
                             % (s, empty, t["rows"], TEXT_MIN))
        if after_fetch and t.get("cand"):
            empty = t["cand"] - t["cand_text"]
            if empty > TEXT_FLAG_SHARE * t["cand"]:
                flags.append("TEXT EMPTY %s %d of %d candidates still have no text after the fetch"
                             % (s, empty, t["cand"]))
    return flags


def record_text(scratch):
    """Called by fetch_desc.py: store the text check on this run's record and replace its TEXT flags.
    Returns the flags. Does nothing when no run is recorded yet (laptop tests with --dry)."""
    data = _load(PATH, {"runs": []})
    if not data["runs"]:
        return []
    rec = data["runs"][-1]
    stats = text_stats(scratch)
    flags = text_flags(stats, after_fetch=True)
    old = rec.get("text", {})
    rec["text"] = {k: dict(old.get(k, {}), **v) for k, v in stats.items()}
    rec["flags"] = [f for f in rec.get("flags", []) if not f.startswith("TEXT EMPTY")] + flags
    json.dump(data, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return flags


NAMES = {"stepstone": "StepStone", "xing": "XING", "linkedin": "LinkedIn"}


def _stepstone_links(scratch):
    """(links, read) from the StepStone collector's TOTAL line, or None."""
    try:
        m = re.search(r"TOTAL (\d+) links, (\d+) read", open(os.path.join(scratch, "stepstone.log"), encoding="utf-8").read())
    except Exception:
        return None
    return (int(m.group(1)), int(m.group(2))) if m else None


def funnel_lines(rec, jobs=()):
    """One line per source for the email, from collection to the jobs sent (7 Oct 2026):
    'StepStone: 548 links, 300 read, 202 collected (202 with text), 40 after filters, 3 after triage (3 with text), 0 sent'."""
    out = []
    for s in TEXT_SOURCES:
        t = (rec or {}).get("text", {}).get(s)
        if not t:
            continue
        bits = []
        if "links" in t:
            bits.append("%d links, %d read" % (t["links"], t["read"]))
        if "rows" in t:
            bits.append("%d collected" % t["rows"] + (" (%d with text)" % t["rows_text"] if s in TEXT_AT_COLLECTION else ""))
        if "filtered" in t:
            bits.append("%d after filters" % t["filtered"])
        if "cand" in t:
            bits.append("%d after triage (%d with text)" % (t["cand"], t["cand_text"]))
        bits.append("%d sent" % sum(1 for j in jobs if (j.get("source") or "").lower() == s))
        out.append("%s: %s" % (NAMES[s], ", ".join(bits)))
    return out


def check(scratch, skipped=()):
    hist = _load(PATH, {"runs": []})["runs"]
    now = datetime.datetime.now(datetime.timezone.utc)
    from slots import slot_for
    rec = dict(at=now.strftime("%Y-%m-%dT%H:%MZ"), date=now.date().isoformat(),
               slot=slot_for(now.hour), sources={}, boards={}, flags=[])
    for s in SOURCES:
        if s in skipped:
            continue
        rows = _load(os.path.join(scratch, s + ".json"), None)
        rec["sources"][s] = len(rows) if isinstance(rows, list) else -1
    for b in _load(os.path.join(scratch, "ats.json.report"), []):
        if not isinstance(b, dict):
            continue
        rec["boards"]["%s|%s" % (b.get("kind"), b.get("slug"))] = [int(b.get("n") or 0), str(b.get("err") or "")]

    flags = rec["flags"]
    for s, n in rec["sources"].items():
        prev = [r["sources"][s] for r in hist[-5:] if r.get("sources", {}).get(s, -1) >= 0]
        if n <= 0:
            flags.append("SOURCE ZERO %s returned no rows%s" % (s, " (file missing)" if n < 0 else ""))
        elif len(prev) >= 3 and n < 0.5 * (sum(prev) / len(prev)):
            flags.append("SOURCE LOW %s %d rows, average of the last %d runs %.0f" % (s, n, len(prev), sum(prev) / len(prev)))
    if not hist:
        # First recorded run: every board is new, so report only the ones that failed.
        bad = [(k, e) for k, (n, e) in sorted(rec["boards"].items()) if e]
        flags.append("FIRST RUN %d boards polled, %d answered, %d failed%s" % (
            len(rec["boards"]), len(rec["boards"]) - len(bad), len(bad),
            ": " + "; ".join("%s (%s)" % (k, e[:40]) for k, e in bad[:25]) if bad else ""))
    for key, (n, err) in sorted(rec["boards"].items()) if hist else []:
        if not any(key in r.get("boards", {}) for r in hist):
            flags.append("BOARD NEW %s %s" % (key, ("error: " + err[:80]) if err else "%d jobs" % n))
            continue
        # 29 Oct 2026: the flag said "3 runs running" on three boards for all 30 recorded runs and
        # nobody acted. It now carries the real count and comes back every tenth run.
        streak = 1
        for r in reversed(hist):
            b = r.get("boards", {}).get(key)
            if not b or bool(b[1]) != bool(err) or (not err and bool(b[0]) != bool(n)):
                break
            streak += 1
        if streak != 3 and streak % 10:
            continue
        if err:
            flags.append("BOARD DEAD %s error %d runs running, fix the slug or set its kind to dead in "
                         "instructions/COMPANIES.md: %s" % (key, streak, err[:80]))
        elif n == 0:
            flags.append("BOARD EMPTY %s 0 jobs %d runs running" % (key, streak))

    rec["text"] = text_stats(scratch)
    flags += text_flags(rec["text"], after_fetch=False)
    # candidates.json holds the filtered pool at this point; fetch_desc.py later stores the triaged one.
    for t in rec["text"].values():
        t["filtered"] = t.pop("cand", 0)
        t.pop("cand_text", None)
    ss = _stepstone_links(scratch)
    if ss and "stepstone" in rec["text"]:
        rec["text"]["stepstone"].update(links=ss[0], read=ss[1])

    cands = _load(os.path.join(scratch, "candidates.json"), [])
    cands = [j for j in cands if isinstance(j, dict)] if isinstance(cands, list) else []
    rec["candidates"] = len(cands)
    trimmed = [dict(rank=i + 1, prescore=j.get("prescore"), company=j.get("company"), title=j.get("title"),
                    source=j.get("source"), date=j.get("date", ""), url=j.get("url") or j.get("apply_url", ""))
               for i, j in enumerate(cands)]
    return hist, rec, trimmed


def main(argv):
    scratch = argv[0]
    dry = "--dry" in argv
    skipped = argv[argv.index("--skipped") + 1].split(",") if "--skipped" in argv else []
    hist, rec, trimmed = check(scratch, skipped)
    for f in rec["flags"]:
        print(f)
    print("health: %d sources, %d boards, %d flags, %d candidates%s"
          % (len(rec["sources"]), len(rec["boards"]), len(rec["flags"]), rec["candidates"],
             " (dry run, nothing recorded)" if dry else ""), file=sys.stderr)
    if dry:
        return
    hist = (hist + [rec])[-KEEP:]
    json.dump({"runs": hist}, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    json.dump(dict(at=rec["at"], slot=rec["slot"], candidates=trimmed),
              open(CANDS, "w", encoding="utf-8"), ensure_ascii=False, indent=0)


def _berlin(at):
    """'2026-09-29T08:03Z' as '10:03 Berlin'. the candidate reads times in Berlin time (29 Sep 2026)."""
    try:
        from zoneinfo import ZoneInfo
        t = datetime.datetime.strptime(at, "%Y-%m-%dT%H:%MZ").replace(tzinfo=datetime.timezone.utc)
        return t.astimezone(ZoneInfo("Europe/Berlin")).strftime("%H:%M Berlin")
    except Exception:
        return ""


def render(root=ROOT, n=14):
    """reports/HEALTH.md: one row per run with rows per source and the reading counts, then the open
    flags and the boards that are failing now. Rebuilt by write_pack.py on every run."""
    runs = _load(os.path.join(root, "state/health.json"), {"runs": []})["runs"][-n:]
    L = ["# Radar health", "",
         "Rebuilt on every run by `scripts/health.py --render` (called from `write_pack.py`). Newest run first. Times are Berlin time.",
         "Rows are what each collector returned before any filter. `cand` is candidates after the filters,",
         "`read` is postings read in full, `unread` is candidates left, `min` is run time, `sent` is jobs in the email.",
         "A dash means the run did not report it. See `state/health.json` for the raw record.", ""]
    cols = ["ba", "ats", "linkedin", "xing", "stepstone", "talent", "arbeitnow", "getro"]
    L.append("| run | " + " | ".join(cols) + " | cand | read | unread | min | sent | flags |")
    L.append("|" + "---|" * (len(cols) + 7))
    for r in reversed(runs):
        sl = _load(os.path.join(root, "shortlists", "%s-%s.json" % (r["date"], r["slot"])), {})
        jobs = sl.get("jobs") if isinstance(sl, dict) else None
        def g(k):
            v = sl.get(k) if isinstance(sl, dict) else None
            return "-" if v in (None, "") else str(v)
        cells = [str(r["sources"].get(c, "-")) if c in r.get("sources", {}) else "-" for c in cols]
        L.append("| %s %s | %s | %s | %s | %s | %s | %s | %d |" % (
            r["date"], "%s %s" % (r["slot"], _berlin(r.get("at", ""))), " | ".join(cells), r.get("candidates", "-"), g("read_full"), g("left_unread"),
            g("minutes"), len(jobs) if isinstance(jobs, list) else "-", len(r.get("flags", []))))
    if runs:
        last = runs[-1]
        L += ["", "## Flags on the latest run (%s %s)" % (last["date"], last["slot"]), ""]
        L += ["- %s" % f for f in last.get("flags", [])] or ["- none"]
        bad = []
        for key, (cnt, err) in sorted(last.get("boards", {}).items()):
            if not err:
                continue
            streak = 0
            for r in reversed(runs):
                if (r.get("boards", {}).get(key) or [0, ""])[1]:
                    streak += 1
                else:
                    break
            bad.append((streak, key, err))
        L += ["", "## Boards failing on the latest run (%d of %d)" % (len(bad), len(last.get("boards", {}))), ""]
        L += ["- %s: %s (failing %d run%s in a row)" % (k, e[:90], st, "" if st == 1 else "s")
              for st, k, e in sorted(bad, reverse=True)] or ["- none"]
    open(os.path.join(root, "reports/HEALTH.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    return len(runs)


def latest_record(date, slot):
    """The run recorded for this date and slot, or None."""
    for r in reversed(_load(PATH, {"runs": []})["runs"]):
        if r.get("date") == date and r.get("slot") == slot:
            return r
    return None


def latest_flags(date, slot):
    """Flags of the run recorded for this date and slot, for the email."""
    r = latest_record(date, slot)
    return r.get("flags", []) if r else None


if __name__ == "__main__":
    if sys.argv[1:2] == ["--render"]:
        print("reports/HEALTH.md rebuilt from %d runs" % render())
    else:
        main(sys.argv[1:])
