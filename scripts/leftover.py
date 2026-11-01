#!/usr/bin/env python3
"""The leftover list: candidates a morning or evening run did not read, for the noon run to finish.

Added 29 Sep 2026 at the candidate's request. Measured that day on the afternoon's collection: 516 rows
passed the title filters, 189 were left after the repeat check, the German drops, the description
fetch and the title triage. The morning run reads about 60 in 45 minutes (52 in 40 minutes on
29 Sep), so well over a hundred stay unread every run. Before this, the noon run collected
everything again, the new postings took the freshness bonus, and the same leftovers stayed unread.

`state/leftover.json` at the repo root holds one candidates.json row per unread job, plus:
    first   "<date> <slot>" of the run that first left it unread
    last    date of the last run that left it unread

`state/backlog_done.json` at the repo root is every job any run read (sent, rejected, also_found), one
entry per job signature, kept DONE_DAYS. A job in it never enters the list again, so the noon run
never reads the same job twice. the candidate chose this on 29 Sep 2026 for the backlog only: morning and
evening still read fresh jobs as before, because a later run sometimes sends a job an earlier run
rejected, and he applied to some of those (scripts/rejected.py).

Every run (write_pack.py calls `after_render`) adds what it read to state/backlog_done.json.
Morning and evening then update the list:
    every job in state/backlog_done.json leaves the list;
    every candidate it did not read is added once. The same job from another source, under
    another id, refreshes the row already there (jobid.is_repeat);
    rows whose `last` is more than KEEP_DAYS old are removed, because they left their
    source's window or the filters caught them since.

Noon (collect_all.py calls `load_for_noon` in place of the collectors):
    the list becomes candidates.json, minus anything read since (state/backlog_done.json), sent since
    (state/seen.json, only sends after the row entered the list: older sends were checked at
    collection, and the filter let second openings through on purpose) or applied to since
    (state/applications.md), sorted by prescore. The rows loaded are recorded in
    leftover_loaded.json in the scratch directory.
Noon render (write_pack.py calls `finish_noon`):
    every loaded row the noon run processed leaves the list. A row counts as processed unless
    it is still in candidates.json and the run did not read it. Rows the noon run did not
    reach stay for the next noon.

    python3 scripts/leftover.py --stats
"""
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from jobid import canonical_id, is_repeat, same_company, same_role, second_opening, sent_match  # noqa: E402

ROOT = os.path.dirname(HERE)
PATH = os.path.join(ROOT, "state/leftover.json")
KEEP_DAYS = 2
DONE_DAYS = 14
from slots import ORDER  # noqa: E402  (one place for the slot rule)


def load(root=ROOT):
    p = os.path.join(root, "state/leftover.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []


def save(rows, root=ROOT):
    json.dump(rows, open(os.path.join(root, "state/leftover.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def load_done(root=ROOT):
    return _jl(os.path.join(root, "state/backlog_done.json"), [])


def record_done(sl, root=ROOT, sc=None):
    """Add every job this run read to state/backlog_done.json, one entry per signature. Returns the count added.

    The shortlist's `rejected` rows carry no link, and the link is what tells a second opening from
    the same job (jobid.second_opening). A row without one takes the link of the candidate with the
    same company and title in this run's candidates.json (review, 29 Sep 2026)."""
    date, slot = sl["date"], sl["slot"]
    done = load_done(root)
    have = {d["sig"] for d in done}
    links = {}
    for c in _jl(os.path.join(sc, "candidates.json"), []) if sc else []:
        links.setdefault(canonical_id(c.get("company") or "", c.get("title") or "", ""), c.get("url") or "")
    n = 0
    for r in read_by(sl):
        sig = canonical_id(r["company"], r["title"], "")
        if not r["url"]:
            r = dict(r, url=links.get(sig, ""))
        if sig in have:
            continue
        have.add(sig)
        done.append(dict(sig=sig, company=r["company"], title=r["title"], url=r["url"], date=date, slot=slot))
        n += 1
    cut = (datetime.date.fromisoformat(date) - datetime.timedelta(days=DONE_DAYS)).isoformat()
    done = [d for d in done if (d.get("date") or "") >= cut]
    json.dump(done, open(os.path.join(root, "state/backlog_done.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return n


def _jl(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def read_by(sl):
    """Every job the run read in full, as the shortlist records it."""
    out = []
    for key in ("jobs", "rejected", "also_found", "borderline"):
        for r in sl.get(key) or []:
            if isinstance(r, dict) and (r.get("company") or r.get("title")):
                out.append(dict(company=r.get("company") or "", title=r.get("title") or "",
                                url=r.get("apply_url") or r.get("url") or ""))
    return out


def _was_read(row, read, live=()):
    """True when a run already read this job. A second opening beside a read job was not read:
    `live` holds the links open when the row was collected, and jobid.second_opening decides, as in
    filter_run.py (review, 29 Sep 2026: once the evening sent Preply "(AI Marketplace)", the unread
    "(AI Learning)" counted as read and left the list)."""
    if not read:
        return False
    m, so = sent_match(row.get("company") or "", row.get("title") or "", "", row.get("url") or "", "", read, live or ())
    return bool(m) and not so


def _key(row):
    return row.get("id") or "%s | %s" % (row.get("company"), row.get("title"))


def save_unread(sc, sl, root=ROOT):
    """Morning and evening. Returns (added, refreshed, removed_read, pruned, size)."""
    date, slot = sl["date"], sl["slot"]
    done = load_done(root)
    import final_check
    live = final_check.pool_urls(sc)
    cands = _jl(os.path.join(sc, "candidates.json"), [])
    # 2 Oct 2026 (docs/PROBLEMS.md 5.4): with a reader log, a row is unread when it has no verdict, by its
    # own id. The match on company and title below counted a row without text as read as soon as a
    # similar job had been read: on 2 Oct, 16 Getro rows that never had a text were kept off the noon
    # list that way. A row without text is unread whatever else is known.
    vd = _jl(os.path.join(sc, "verdicts.json"), None)
    if isinstance(vd, dict):
        unread = [c for c in cands if (c.get("id") or "") not in vd]
    else:
        unread = [c for c in cands if not (c.get("desc") or "").strip() or not _was_read(c, done, live)]
    pool = load(root)
    before = len(pool)
    pool = [e for e in pool if not _was_read(e, done, live | set(e.get("twin_live_urls") or []))]
    removed_read = before - len(pool)
    at = {_key(e): i for i, e in enumerate(pool)}
    added = refreshed = 0
    twins = _twin_links(sc, root, sl)
    for c in unread:
        tw = twins(c)
        if tw:
            c = dict(c, twin_live_urls=tw)
        i = at.get(_key(c))
        if i is None and pool:
            m = is_repeat(c.get("company") or "", c.get("title") or "", "", pool, c.get("url") or "")
            # The same job under another id (another source) is one row. Two openings at one
            # employer are two rows, by the rule filter_run.py uses (review, 29 Sep 2026: Preply
            # "(AI Learning)" and "(AI Marketplace)" were folded into one and the first was lost).
            if m and second_opening(c.get("url"), c.get("title"), dict(m, urls=[m.get("url")]), live):
                m = None
            i = next((k for k, e in enumerate(pool) if e is m), None) if m else None
        if i is not None:
            pool[i] = dict(c, id=pool[i].get("id", c.get("id")), first=pool[i].get("first"), last=date)
            refreshed += 1
        else:
            at[_key(c)] = len(pool)
            pool.append(dict(c, first="%s %s" % (date, slot), last=date))
            added += 1
    cut = (datetime.date.fromisoformat(date) - datetime.timedelta(days=KEEP_DAYS)).isoformat()
    kept = [e for e in pool if (e.get("last") or "") >= cut]
    save(kept, root)
    return added, refreshed, removed_read, len(pool) - len(kept), len(kept)


def _twin_links(sc, root, sl=None):
    """The links, live in this run's pool, of a sent job the row resembles. At noon there is no pool,
    and without them jobid.second_opening, which needs the sent job's link in the pool, would call a
    second opening a repeat: in final_check.py, and in load_for_noon when the twin was sent after the
    row entered the list (review, 29 Sep 2026). Two cases: a row the filter already let through
    beside an earlier send (similar_to_sent), and a row whose twin this run is sending now."""
    import final_check
    from jobid import _links
    urls = final_check.pool_urls(sc)
    seen = _jl(os.path.join(root, "state/seen.json"), [])
    sending = [dict(company=j.get("company") or "", title=j.get("title") or "", url=j.get("apply_url") or "",
                    urls=[u for u in (j.get("apply_url"), j.get("fallback_url"), j.get("url"),
                                      j.get("linkedin_url"), j.get("xing_url"), j.get("ba_url")) if u])
               for j in (sl or {}).get("jobs") or [] if isinstance(j, dict)]

    def twins(c):
        found = set()
        for lst, when in ((seen, c.get("similar_to_sent")), (sending, sending)):
            if not when:
                continue
            m = is_repeat(c.get("company") or "", c.get("title") or "", c.get("location", ""), lst,
                          c.get("url") or "", c.get("desc") or "")
            if m:
                found |= {x for x in _links(m) if x in urls}
        return sorted(found)
    return twins


def _applied(root):
    import applications
    return applications.applied(os.path.join(root, "state/applications.md"))


def load_for_noon(sc, root=ROOT):
    """Noon. Writes candidates.json from the list. Returns (loaded, sent_since, applied_since)."""
    import prescore
    pool = load(root)
    done = load_done(root)
    seen = _jl(os.path.join(root, "state/seen.json"), [])
    apps = _applied(root)
    cands, sent, applied, live = [], 0, 0, []
    for e in pool:
        co, ti = e.get("company") or "", e.get("title") or ""
        if any(same_company(c, co) and same_role(t, ti, c) for c, t in apps):
            applied += 1
            continue
        if _was_read(e, done, set(e.get("twin_live_urls") or [])):
            sent += 1
            continue
        m, so = sent_match(co, ti, e.get("location", ""), e.get("url", ""), e.get("desc", ""),
                           _sent_after(seen, e.get("first", "")), set(e.get("twin_live_urls") or []))
        if m and not so:
            sent += 1
            continue
        cands.append({k: v for k, v in e.items() if k not in ("first", "last", "twin_live_urls")})
        live += e.get("twin_live_urls") or []
    json.dump(prescore.order(cands), open(os.path.join(sc, "candidates.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump([_key(e) for e in pool], open(os.path.join(sc, "leftover_loaded.json"), "w", encoding="utf-8"))
    # final_check.py reads this as the pool, so a second opening stays a second opening at noon.
    json.dump(sorted(set(live)), open(os.path.join(sc, "pool_urls.json"), "w", encoding="utf-8"))
    return len(cands), sent, applied


def _sent_after(seen, first):
    """Sends made after the run that put the row on the list. An entry without a slot, on that
    same date, counts as after (written before 29 Sep 2026, when state/seen.json had no slot)."""
    d, _, s = (first or "").partition(" ")
    if not d:
        return seen
    return [e for e in seen if (e.get("sent") or "") > d or ((e.get("sent") or "") == d and
            ORDER.get(e.get("slot"), 9) > ORDER.get(s, -1))]


def finish_noon(sc, sl, root=ROOT):
    """Noon render. Returns (processed, still_unread, size)."""
    loaded = set(_jl(os.path.join(sc, "leftover_loaded.json"), []))
    done = load_done(root)
    import final_check
    live = final_check.pool_urls(sc)
    left = {_key(c) for c in _jl(os.path.join(sc, "candidates.json"), []) if not _was_read(c, done, live)}
    pool = load(root)
    kept = [e for e in pool if _key(e) not in loaded or _key(e) in left]
    save(kept, root)
    return len(pool) - len(kept), len([e for e in kept if _key(e) in loaded]), len(kept)


def after_render(sc, sl, root=ROOT):
    """Called by write_pack.py. Returns the line to print, or None for a render outside a run."""
    if not os.path.exists(os.path.join(sc, "run_slot.json")):
        return None
    n_done = record_done(sl, root, sc)
    # The backlog path is for a noon run that loaded the backlog. A noon run forced to collect
    # (collect_all.py --collect) has no leftover_loaded.json and saves its unread rows like any
    # collecting run (review, 29 Sep 2026).
    if sl.get("slot") == "noon" and os.path.exists(os.path.join(sc, "leftover_loaded.json")):
        done, still, size = finish_noon(sc, sl, root)
        return ("state/leftover.json: noon processed %d, %d still unread, %d in the list; state/backlog_done.json +%d"
                % (done, still, size, n_done))
    added, refreshed, gone, pruned, size = save_unread(sc, sl, root)
    return ("state/leftover.json: %d added, %d refreshed, %d read (this or an earlier run) and removed, "
            "%d older than %d days removed, %d in the list; state/backlog_done.json +%d"
            % (added, refreshed, gone, pruned, KEEP_DAYS, size, n_done))


if __name__ == "__main__":
    rows = load()
    by = {}
    for r in rows:
        by[r.get("first", "?")] = by.get(r.get("first", "?"), 0) + 1
    print("%d rows in state/leftover.json" % len(rows))
    for k in sorted(by):
        print("  first left unread %s: %d" % (k, by[k]))
