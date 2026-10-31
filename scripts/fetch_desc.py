#!/usr/bin/env python3
"""Full descriptions for the rows that arrive without one, fetched after the title triage.

Added 29 Sep 2026 at the candidate's request. A run now narrows the list in three steps. filter_run.py
drops by title and by the descriptions the collectors bring. The agent's title triage
(scripts/triage.py) cleans what is left. This script then fetches the full text for the clean
rows. Bundesagentur, LinkedIn and talent.com rows carry no description until this point, so the
German drop and the prescore could not see them. On 29 Sep 118 of the 425 rows the morning run
left unread were Bundesagentur rows.

Measured from the laptop on 29 Sep 2026. 120 BA detail calls took 7 seconds with 8 threads and
none failed. `hard_drop` flagged 31 of those 120 raw rows, and none of the 31 BA packs ever sent.

    python3 scripts/fetch_desc.py $SC

2 Oct 2026: every row without a description is fetched now, from any source. Rows no source
reader covers go through scripts/jobpage.py, which reads the posting from its link (the ATS's API,
the page's JSON-LD, or the page's main content). Nothing is cut at any length.

Writes the descriptions into candidates.json and sorts it again by prescore. Rows whose text
states a strong German requirement move to german_off_fetched.json with the sentence, as in
filter_run.py. A row whose fetch fails stays in the list without a description and is listed in no_text.json
with the reason. The last line printed is the text check: how many candidates have the full text.
"""
import concurrent.futures as cf
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prescore
from lang_band import german
import clearance
from trim_desc import trim

# Keys a reader returns that describe the fetch, not the job.
FETCH_KEYS = {"desc", "desc_cut", "ok", "err", "error", "band", "lang_line", "desc_src"}
# LinkedIn answers 429 when pushed, so it gets the same 3 threads read_linkedin.py uses.
WORKERS = {"Bundesagentur": 8, "linkedin": 3, "talent.com": 8, "*": 8}
# 2 Oct 2026: every row without a description is fetched, whatever its source. "*" is the reader
# for a row no other reader covers: scripts/jobpage.py, which reads the posting from its link.
# Until then Getro, SmartRecruiters, JOIN, Avature, Breezy and the Personio boards that publish
# no text in their feed went to the reading step empty (95 of 411 candidates on 2 Oct).
ANY = "*"
# Shorter than this is not a posting: "siehe Homepage", a login wall, a one-line teaser. Such a row
# is fetched again from its link, and the longer text is kept.
THIN = 300


def readers():
    import read_jobs, read_linkedin, read_talent, jobpage
    return {"Bundesagentur": read_jobs.one, "linkedin": read_linkedin.one, "talent.com": read_talent.one,
            ANY: jobpage.one}


def text_of(r):
    """The description a reader returned, or "" when the fetch failed."""
    if not r or r.get("error") or r.get("err"):
        return ""
    d = r.get("desc") or ""
    return "" if d.startswith("FETCH FAILED") else d


def why_of(r):
    """Why a fetch returned no text, in a few words."""
    if not r:
        return "no reader for this source"
    d = r.get("desc") or ""
    return str(r.get("error") or r.get("err") or (d if d.startswith("FETCH FAILED") else "") or "the source returned no text")[:200]


def group(src):
    """The label a source is counted under in the summary line."""
    src = src or ""
    return "boards" if src.startswith("ATS/") else "getro" if src.startswith("getro") else src


def _safe(fn, j):
    """One row's fetch. A row a reader cannot handle (a LinkedIn row without li_id raised KeyError
    outside the reader's try) fails alone instead of stopping every other fetch (review, 29 Sep 2026)."""
    try:
        return fn(j)
    except Exception as ex:
        return {"error": "%s: %s" % (type(ex).__name__, str(ex)[:80])}


def _fetch(part, fn, workers):
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        return list(zip(part, ex.map(lambda j: _safe(fn, j), part)))


def run(sc, fetchers=None):
    fetchers = fetchers or readers()
    path = os.path.join(sc, "candidates.json")
    rows = json.load(open(path, encoding="utf-8"))
    anyfn = fetchers.get(ANY)

    def reader(j):
        return j.get("source") if j.get("source") in fetchers else (ANY if anyfn else None)

    todo = [j for j in rows if len(j.get("desc") or "") < THIN and reader(j)]
    got = {}
    for src, fn in fetchers.items():
        part = [j for j in todo if reader(j) == src]
        for j, r in _fetch(part, fn, WORKERS.get(src, 4)):
            got[id(j)] = r
    # A source reader that came back empty or thin gets one more try from the row's own links: a BA
    # row often says "apply on our site" and carries the employer's link in `externe_url`.
    if anyfn:
        again = [j for j in todo if reader(j) != ANY and len(text_of(got.get(id(j)))) < THIN]
        merged = [dict(j, **{k: v for k, v in (got.get(id(j)) or {}).items() if k not in FETCH_KEYS}) for j in again]
        for (j, m), (_, r) in zip(zip(again, merged), _fetch(merged, anyfn, WORKERS[ANY])):
            if len(text_of(r)) > len(text_of(got.get(id(j)))):
                keep = {k: v for k, v in (got.get(id(j)) or {}).items() if k not in FETCH_KEYS}
                got[id(j)] = dict(r, **keep)
    kept, german_off, failed, gone, repeats, clearance_off = [], [], [], [], [], []
    # 2 Oct 2026: a card row (Bundesagentur, LinkedIn, talent.com, Getro) had no text when filter_run.py
    # looked for repeats, so a job listed under another company name got through (docs/PROBLEMS.md 5.2:
    # HUK-COBURG as "Mecklenburgische Versicherungs-Gesellschaft", ARRK as "Mitsui Chemicals Group").
    # Its text names the real employer, so the same check runs again here, with the text.
    seen, pool_urls, sent_prints = _repeat_data(sc)
    for j in rows:
        if id(j) not in got:
            kept.append(j)
            continue
        r = got[id(j)]
        full = text_of(r)
        if not full and r.get("gone"):
            # The posting's own link answers 404, 410 or "closed". It is no longer a job, so it
            # leaves the list here and is not counted as unread.
            gone.append((j, why_of(r)))
            continue
        if len(full) <= len(j.get("desc") or ""):
            # Nothing better than what the row already had. It stays, and is reported as without text.
            failed.append((j, why_of(r) if not full else "only %d characters found" % len(full)))
            kept.append(j)
            continue
        j.update({k: v for k, v in r.items() if k not in FETCH_KEYS})
        twin = _repeat(j, full, seen, pool_urls, sent_prints)
        if twin:
            repeats.append((j, twin))
            continue
        verdict, lines = ("ok", []) if j.get("referral") else german(full)
        line = lines[0] if verdict == "drop" else None
        j.pop("german_decide", None)
        if verdict == "decide":
            # Unclear German line: the row stays, and the agent must quote the line and decide.
            j["german_decide"] = lines[:3]
        cv, clines = ("ok", []) if j.get("referral") else clearance.check(full)
        j.pop("clearance_flag", None)
        if cv == "flag":
            j["clearance_flag"] = clines[:2]
        j["desc"], j["desc_cut"] = trim(full)
        j["desc_len"] = len(full)
        j["desc_src"] = r.get("desc_src") or j.get("source") or ""
        j["desc_fetched"] = True
        if len(full) < THIN:
            failed.append((j, "only %d characters found" % len(full)))
        if line:
            german_off.append((j, line))
        elif cv == "drop":
            clearance_off.append((j, clines[0]))
        else:
            kept.append(j)
    kept = prescore.order(kept)
    json.dump(kept, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump([{"job": j["company"] + " | " + j["title"], "source": j.get("source"), "url": j.get("url"), "line": l}
               for j, l in german_off],
              open(os.path.join(sc, "german_off_fetched.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # Rows the run must not call read: no text could be fetched for them.
    json.dump([{"job": "%s | %s" % (j.get("company"), j.get("title")), "source": j.get("source"),
                "url": j.get("url"), "why": w} for j, w in failed],
              open(os.path.join(sc, "no_text.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump([{"job": "%s | %s" % (j.get("company"), j.get("title")), "source": j.get("source"),
                "url": j.get("url"), "why": w} for j, w in gone],
              open(os.path.join(sc, "gone.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump([{"job": "%s | %s" % (j.get("company"), j.get("title")), "source": j.get("source"), "url": j.get("url"), "line": l}
               for j, l in clearance_off],
              open(os.path.join(sc, "clearance_off_fetched.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump([{"job": "%s | %s" % (j.get("company"), j.get("title")), "source": j.get("source"), "url": j.get("url"),
                "matched": "%s | %s (sent %s)" % (m.get("company"), m.get("title"), m.get("sent"))} for j, m in repeats],
              open(os.path.join(sc, "repeats_after_fetch.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    by_src = {}
    bad = {id(j) for j, _ in failed} | {id(j) for j, _ in gone}
    for j in todo:
        g = group(j.get("source"))
        by_src.setdefault(g, [0, 0])[0] += 1
        if id(j) not in bad:
            by_src[g][1] += 1
    return dict(asked=len(todo), fetched=len(todo) - len(failed) - len(gone), failed=len(failed), gone=len(gone),
                german=len(german_off), clearance=len(clearance_off), repeats=len(repeats), left=len(kept), by_source=by_src)


def _repeat_data(sc):
    """state/seen.json, the links live in this run's pool, and the fingerprints of the sent packs."""
    try:
        import decisions
        import final_check
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        seen = json.load(open(os.path.join(root, "state/seen.json"), encoding="utf-8"))
        return seen, final_check.pool_urls(sc), decisions.sent_prints(root)
    except Exception:
        return [], set(), []


def _repeat(j, text, seen, pool_urls, sent_prints):
    """The sent job this fetched row repeats, or None. A second opening is not a repeat."""
    if not seen and not sent_prints:
        return None
    try:
        import decisions
        from jobid import is_repeat, second_opening
        m = is_repeat(j.get("company") or "", j.get("title") or "", j.get("location", ""), seen, j.get("url") or "", text)
        if m and second_opening(j.get("url"), j.get("title"), m, pool_urls):
            m = None
        return m or decisions.text_twin(j.get("title") or "", text, sent_prints)
    except Exception:
        return None


def report(sc):
    """One line on the state of every candidate's text, for the run log and the coverage table."""
    rows = json.load(open(os.path.join(sc, "candidates.json"), encoding="utf-8"))
    n = len(rows)
    lens = sorted((j.get("desc_len") or len(j.get("desc") or "")) for j in rows)
    none = sum(1 for j in rows if len(j.get("desc") or "") < THIN)
    words = sum(len((j.get("desc") or "").split()) for j in rows)
    return ("text check: %d candidates, %d with the full text, %d without text (no_text.json); "
            "median %d characters, longest %d, %d words to read in all"
            % (n, n - none, none, lens[n // 2] if n else 0, lens[-1] if n else 0, words))


if __name__ == "__main__":
    s = run(sys.argv[1])
    print("descriptions fetched: %d of %d (%s), %d failed and kept in the list (no_text.json), "
          "%d postings closed and removed (gone.json), %d sent before under another name or link "
          "(repeats_after_fetch.json); "
          "German required, dropped after fetch: %d (german_off_fetched.json); "
          "nationality or clearance required, dropped after fetch: %d (clearance_off_fetched.json); %d left to read"
          % (s["fetched"], s["asked"], ", ".join("%s %d/%d" % (k, v[1], v[0]) for k, v in s["by_source"].items()),
             s["failed"], s["gone"], s["repeats"], s["german"], s["clearance"], s["left"]))
    print(report(sys.argv[1]))
    # 7 Oct 2026: per-source text check for StepStone, XING and LinkedIn, stored on this run's
    # health record so the email shows it (scripts/health.py, record_text).
    try:
        import health
        for f in health.record_text(sys.argv[1]):
            print(f)
        r = json.load(open(health.PATH, encoding="utf-8"))["runs"][-1]
        for line in health.funnel_lines(r):
            print(line)
    except Exception as ex:
        print("text check not recorded: %s" % str(ex)[:80])
