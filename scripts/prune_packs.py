#!/usr/bin/env python3
"""Delete packs for jobs he never applied to once the job is really gone.

Added 29 Sep 2026 at the candidate's request. jobs/ only grows, and on that day 100 of the 172 packs
he had not applied to were two to three weeks old, so the batch backlog was mostly jobs that
may have closed.

A pack is deleted only when all of these hold:
  1. it was sent MIN_AGE days ago or more;
  2. state/applications.md has no applied row for that company and role;
  3. every link it has (apply_url, fallback_url) checks GONE with check_live.py, so one LIVE or
     UNSURE link keeps it;
  4. the job is not in this run's collected pool. This guard is the measured one: on 29 Sep,
     9 of the unapplied packs checked GONE and 2 of those 9 were still being collected that day
     under a new link (Böttcher AG reposted on the Bundesagentur with a new reference, Nerdware's
     arbeitnow copy expired while the job stayed up). A dead link is not a dead job;
  5. it was GONE on an earlier check too, at least STRIKE_GAP days before. One outage or one bad
     answer never deletes anything.

It runs every EVERY_DAYS days (`last` in the state file; a dry run is never skipped).
State is state/prune.json: `pending` holds the first GONE check per pack, `log` the deletions. A pack
that is LIVE, UNSURE or in the pool again is taken off `pending`. state/seen.json keeps its entry, so
a deleted job is still never sent twice. The file is gone from the tree but stays in git history.

    python3 scripts/prune_packs.py <scratch>          check, strike, delete
    python3 scripts/prune_packs.py <scratch> --dry    check and report, change nothing
"""
import datetime, json, os, sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from jobid import is_repeat, same_company, same_role  # noqa: E402
from applications import applied as applied_rows  # noqa: E402

ROOT = os.path.dirname(HERE)
MIN_AGE = 3  # 29 Oct 2026: was 20, which never touched his 14-day batch backlog
EVERY_DAYS = 2  # 29 Oct 2026, the candidate: the backlog refresh runs every second evening, not daily
STRIKE_GAP = 1
POOL_FILES = ["ats", "ba", "linkedin", "xing", "stepstone", "talent", "arbeitnow", "getro"]


def _load(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def pool_rows(scratch):
    rows = []
    for f in POOL_FILES:
        data = _load(os.path.join(scratch, f + ".json"), [])
        if not isinstance(data, list):
            continue
        for x in data:
            if isinstance(x, dict):
                rows.append(dict(company=x.get("company") or "", title=x.get("title") or "",
                                 location=x.get("location") or "", url=x.get("url") or ""))
    return rows


def failed_boards(scratch):
    """(company, slug) of every board that errored in this run's collection."""
    rep = _load(os.path.join(scratch, "ats.json.report"), [])
    return [(str(b.get("company") or ""), str(b.get("slug") or "")) for b in rep
            if isinstance(b, dict) and b.get("err")]


def packs(root):
    idx = _load(os.path.join(root, "jobs", "index.json"), [])
    return [p for p in idx if isinstance(p, dict) and p.get("pack")] if isinstance(idx, list) else []


def verdict(results):
    """GONE only when there is at least one link and every link is GONE."""
    return "GONE" if results and all(r[0] == "GONE" for r in results) else \
        "LIVE" if any(r[0] == "LIVE" for r in results) else "UNSURE"


def run(scratch, root=ROOT, today=None, dry=False, check=None, apps=None):
    today = today or datetime.date.today()
    if check is None:
        import check_live
        check = check_live.check
    state = _load(os.path.join(root, "state/prune.json"), {"pending": {}, "log": []})
    pending, log = state.setdefault("pending", {}), state.setdefault("log", [])
    last = state.get("last")
    if not dry and last and (today - datetime.date.fromisoformat(last)).days < EVERY_DAYS:
        return {"skipped": last}, {}, []
    applied = applied_rows(apps or os.path.join(root, "state/applications.md"))
    pool = pool_rows(scratch)
    # A board that failed this run cannot vouch for its jobs, so the pool guard is blind for them
    # (review, 29 Sep 2026: ATOSS's Greenhouse board failed DNS and its pack was deleted anyway).
    failed = failed_boards(scratch)

    def board_failed(p):
        u = (p.get("apply_url") or "").lower() + " " + (p.get("fallback_url") or "").lower()
        return any((len(sl) >= 3 and sl.lower() in u) or (co and same_company(co, p.get("company", "")))
                   for co, sl in failed)
    cut = (today - datetime.timedelta(days=MIN_AGE)).isoformat()

    todo, kept = [], {"young": 0, "applied": 0}
    for p in packs(root):
        if str(p.get("sent") or "9999")[:10] > cut:
            kept["young"] += 1
            continue
        # Loose on purpose (review, 29 Sep 2026): he edits titles in state/applications.md, and a strict
        # match let four applied packs through (Delivery Hero, NiCE, Libra, TÜV SÜD). A wrong
        # loose match only keeps a pack. pick.py also stamps `applied` into the pack itself.
        if str(p.get("applied") or "").strip() or any(
                same_company(c, p.get("company", "")) and same_role(t, p.get("title", ""), c, loose=True)
                for c, t in applied):
            kept["applied"] += 1
            continue
        todo.append(p)

    def one(p):
        urls = [u for u in (p.get("apply_url"), p.get("fallback_url")) if u]
        res = [check(u) for u in urls]
        in_pool = bool(pool) and bool(is_repeat(p.get("company", ""), p.get("title", ""), p.get("location", ""),
                                               pool, p.get("apply_url") or ""))
        return p, res, in_pool

    with ThreadPoolExecutor(12) as ex:
        checked = list(ex.map(one, todo))

    counts = {"live": 0, "unsure": 0, "in_pool": 0, "first_strike": 0, "deleted": 0, "no_pool": 0, "board_failed": 0}
    deleted = []
    for p, res, in_pool in checked:
        pid = os.path.basename(p["pack"])[:-3]
        v = verdict(res)
        if v != "GONE" or in_pool:
            counts["in_pool" if in_pool else v.lower()] += 1
            pending.pop(pid, None)
            continue
        if not pool:
            # Without a collected pool the repost guard cannot run. Never delete on links alone.
            counts["no_pool"] += 1
            continue
        if board_failed(p):
            counts["board_failed"] += 1
            continue
        first = pending.get(pid, {}).get("first")
        if not first:
            pending[pid] = dict(first=today.isoformat(), company=p.get("company"), title=p.get("title"),
                                reasons=[r[1] for r in res])
            counts["first_strike"] += 1
            continue
        if (today - datetime.date.fromisoformat(first)).days < STRIKE_GAP:
            continue
        path = os.path.join(root, p["pack"])
        entry = dict(date=today.isoformat(), pack=p["pack"], company=p.get("company"), title=p.get("title"),
                     sent=p.get("sent"), first_gone=first, reasons=[r[1] for r in res])
        if not dry and os.path.exists(path):
            os.remove(path)
            pending.pop(pid, None)
            log.append(entry)
        deleted.append(entry)
        counts["deleted"] += 1

    state["log"] = log[-300:]
    if not dry:
        state["last"] = today.isoformat()
        json.dump(state, open(os.path.join(root, "state/prune.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if counts["deleted"]:
            # Rebuild jobs/index.json so pick.py never lists a deleted pack (review, 29 Sep 2026).
            try:
                from write_pack import reindex
                reindex(root)
            except Exception as ex:
                print("index not rebuilt after pruning: %s" % str(ex)[:80], file=sys.stderr)
    return counts, kept, deleted


def main(argv):
    scratch = argv[0]
    dry = "--dry" in argv
    counts, kept, deleted = run(scratch, dry=dry)
    if "skipped" in counts:
        print("prune: skipped, last check %s, it runs every %d days" % (counts["skipped"], EVERY_DAYS), file=sys.stderr)
        return
    for d in deleted:
        print("PRUNED%s %s | %s | sent %s, gone since %s (%s)" % (
            " (dry)" if dry else "", d["company"], d["title"], d["sent"], d["first_gone"], "; ".join(d["reasons"])))
    print("prune: %d old unapplied packs checked, %d live, %d unsure, %d back in the pool, %d first strike, "
          "%d deleted, %d skipped with no pool, %d skipped because their board failed this run; "
          "kept %d younger than %d days and %d applied%s"
          % (sum(counts[k] for k in ("live", "unsure", "in_pool", "first_strike", "deleted", "no_pool", "board_failed")),
             counts["live"], counts["unsure"], counts["in_pool"], counts["first_strike"], counts["deleted"],
             counts["no_pool"], counts["board_failed"], kept["young"], MIN_AGE, kept["applied"],
             " (dry run)" if dry else ""), file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
