#!/usr/bin/env python3
"""Memory of every job a run read, with its verdict, so no run reads the same job twice.

Added 2 Oct 2026 (docs/PROBLEMS.md 4.1, 4.2, 5.1, 2.8). Each run used to read and score the whole
pool again. Counted from the shortlists of 30 Sep to 2 Oct: 767 reads of 342 distinct jobs, and in
the last four full runs 367 of 502 reads (73%) were jobs an earlier run had already read. The
same job came out differently from run to run (195 jobs), and 13 jobs one run rejected were sent
by another. A full read of about 190 jobs is about 127,000 words and does not fit in one agent.
With this memory a run reads the 15 to 50 jobs that are new, in full.

`state/decisions.json` at the repo root holds one entry per job read:
    {"key", "company", "title", "url", "verdict", "fit", "gate", "band", "lang_line", "reason",
     "date", "slot", "chars", "print"}

`verdict` is send, also, borderline or reject. `print` is a fingerprint of the text that was read.

filter_run.py calls `split` on the candidates. A candidate that matches an entry from the last DAYS
days leaves the list and is written to remembered.json with the old verdict. It is read again when:
    - its text changed (the fingerprint shares less than SAME of its values with the stored one),
    - the entry is older than DAYS,
    - it is a second opening beside the remembered job (two links live at once, titles differ),
    - or the entry was removed with `forget`.
The German and clearance checks do not depend on this memory. They run on the current text of
every job a run is about to send (final_check.py), so an edit that adds a requirement is caught.

write_pack.py calls `record` after a render, which stores the run's verdicts.

    python3 scripts/decisions.py --stats
    python3 scripts/decisions.py forget "<company>" "<title words>"     a wrong verdict, read it again
"""
import datetime
import json
import os
import re
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from jobid import canonical_id, is_repeat, norm_url, second_opening  # noqa: E402

ROOT = os.path.dirname(HERE)
DAYS = 14       # a verdict is reused this long, then the job is read once more
KEEP = 45       # entries older than this are removed from the file
SAME = 0.6      # share of the fingerprint that must match for "the same text"
PRINT_N = 32


def path(root=ROOT):
    return os.path.join(root, "state/decisions.json")


def load(root=ROOT):
    try:
        rows = json.load(open(path(root), encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def save(rows, root=ROOT):
    json.dump(rows, open(path(root), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def fingerprint(text):
    """PRINT_N numbers that stay mostly the same when a text is lightly edited or comes from another
    board with another footer, and change when the posting is rewritten. [] for no text.
    (A min-hash over three-word runs. Two texts share about as many numbers as they share runs.)"""
    words = re.findall(r"[0-9a-zà-ÿ]+", (text or "").lower())
    if len(words) < 20:
        return []
    runs = {" ".join(words[i:i + 3]).encode("utf-8") for i in range(len(words) - 2)}
    return [min(zlib.crc32(r, seed) for r in runs) for seed in range(PRINT_N)]


def same_text(a, b):
    """True, False, or None when one side has no fingerprint (a card with no text yet)."""
    if not a or not b:
        return None
    return sum(1 for x, y in zip(a, b) if x == y) / float(PRINT_N) >= SAME


def active(rows, today, days=DAYS):
    cut = (datetime.date.fromisoformat(today) - datetime.timedelta(days=days)).isoformat()
    return [r for r in rows if (r.get("date") or "") >= cut]


def split(cands, rows, today, pool_urls=(), days=DAYS):
    """(kept, remembered). remembered is a list of (candidate, entry). A candidate whose text
    changed stays in `kept` with `text_changed` set to the old verdict, so the reader shows it."""
    act = active(rows, today, days)
    exact = {}
    for r in act:
        exact.setdefault(r.get("key"), []).append(r)
    kept, remembered = [], []
    for j in cands:
        # The job's own entries first. An employer can post one title several times with different
        # texts (Mistral "AI Scientist" per team, typeform per country), and each text read has its
        # own entry. The looser match below is for the same job under another company spelling.
        own = exact.get(canonical_id(j.get("company") or "", j.get("title") or "", "")) or []
        if not own and act:
            m = is_repeat(j.get("company") or "", j.get("title") or "", j.get("location", ""), act, j.get("url") or "", "")
            own = [m] if m else []
        own = [m for m in own if not second_opening(j.get("url"), j.get("title"), m, pool_urls)]
        if not own:
            kept.append(j)
            continue
        mine = fingerprint(j.get("desc") or "")
        u = norm_url(j.get("url") or "")
        hit = next((m for m in own if u and u == m.get("url")), None) if not mine else None
        hit = hit or next((m for m in own if same_text(mine, m.get("print"))), None)
        if hit is None and (not mine or all(not m.get("print") for m in own)):
            hit = own[0]                               # nothing to compare: a card, or an entry read without text
        if hit is None:
            m = own[0]
            j["text_changed"] = "read %s as %s (fit %s); the text has changed since" % (m.get("date"), m.get("verdict"), m.get("fit"))
            kept.append(j)
            continue
        remembered.append((j, hit))
    return kept, remembered


def record(verdicts, cands, date, slot, root=ROOT):
    """Store one run's verdicts. `verdicts` is {id: verdict row} from verdicts.json, `cands` the rows
    of candidates.json. Returns the number of entries added or updated."""
    rows = load(root)
    by_id = {c.get("id"): c for c in cands if c.get("id")}
    # One entry per job and link: the same title posted twice with different texts keeps both.
    at = {(r.get("key"), r.get("url")): i for i, r in enumerate(rows)}
    n = 0
    for cid, v in (verdicts or {}).items():
        c = by_id.get(cid) or {}
        co, ti = v.get("company") or c.get("company") or "", v.get("title") or c.get("title") or ""
        if not co and not ti:
            continue
        key = canonical_id(co, ti, "")
        text = c.get("desc") or ""
        entry = dict(key=key, company=co, title=ti, location=c.get("location", ""), url=norm_url(c.get("url") or v.get("url") or ""),
                     verdict=v.get("verdict"), fit=v.get("fit"), gate=v.get("gate") or "", band=v.get("band") or "",
                     lang_line=(v.get("lang_line") or "")[:300], reason=(v.get("reason") or "")[:300],
                     hard_req=(v.get("hard_req") or "")[:300],
                     date=date, slot=slot, chars=c.get("desc_len") or len(text), print=fingerprint(text))
        k = (key, entry["url"])
        if k in at:
            rows[at[k]] = entry
        else:
            at[k] = len(rows)
            rows.append(entry)
        n += 1
    cut = (datetime.date.fromisoformat(date) - datetime.timedelta(days=KEEP)).isoformat()
    rows = [r for r in rows if (r.get("date") or "") >= cut]
    save(rows, root)
    return n


TWIN = 0.5      # share of the fingerprint two copies of one posting must share
TWIN_DAYS = 60


def sent_prints(root=ROOT, today=None, days=TWIN_DAYS):
    """(seen entry, fingerprint of its pack text) for every job sent in the last `days` days."""
    today = today or datetime.date.today().isoformat()
    cut = (datetime.date.fromisoformat(today) - datetime.timedelta(days=days)).isoformat()
    try:
        seen = json.load(open(os.path.join(root, "state/seen.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for e in seen:
        if (e.get("sent") or "") < cut or not e.get("pack"):
            continue
        try:
            body = open(os.path.join(root, e["pack"]), encoding="utf-8").read().split("## Full job description", 1)[-1]
        except OSError:
            continue
        fp = fingerprint(body)
        if fp:
            out.append((e, fp))
    return out


def text_twin(title, text, prints):
    """The sent job this row is a copy of, or None: the same title and the same text, whatever the
    company is called. docs/PROBLEMS.md 5.2: ARRK came back as "Mitsui Chemicals Group", HUK-COBURG as
    "Mecklenburgische Versicherungs-Gesellschaft", knuspr as Rohlik, and two recruiters posted one
    client's job. Measured 2 Oct 2026 on the 505 sent packs: of 2,291 pairs with the same title at
    different companies, two share more than a quarter of their fingerprint (1.00 and 0.97, both the
    same job posted twice) and every other pair shares 0.16 or less."""
    from jobid import same_title
    mine = fingerprint(text)
    if not mine:
        return None
    for e, fp in prints:
        if sum(1 for x, y in zip(mine, fp) if x == y) / float(PRINT_N) >= TWIN and same_title(e.get("title") or "", title or ""):
            return e
    return None


def forget(company, title, root=ROOT):
    """Remove the entries for a job so the next run reads it again. Returns what was removed."""
    rows = load(root)
    words = [w for w in re.findall(r"[0-9a-zà-ÿ]+", (title or "").lower()) if len(w) >= 3]
    gone = [r for r in rows if (company or "").lower() in (r.get("company") or "").lower()
            and all(w in (r.get("title") or "").lower() for w in words)]
    save([r for r in rows if r not in gone], root)
    return gone


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "forget":
        gone = forget(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
        for r in gone:
            print("forgotten: %s | %s (%s, fit %s, %s)" % (r["company"], r["title"], r.get("verdict"), r.get("fit"), r.get("date")))
        print("%d entries removed. The next run reads %s again." % (len(gone), "them" if len(gone) != 1 else "it"))
    else:
        rows = load()
        today = datetime.date.today().isoformat()
        act = active(rows, today)
        by = {}
        for r in act:
            by[r.get("verdict")] = by.get(r.get("verdict"), 0) + 1
        print("%d entries, %d from the last %d days (%s)" % (
            len(rows), len(act), DAYS, ", ".join("%s %d" % kv for kv in sorted(by.items(), key=lambda x: str(x[0]))) or "none"))
