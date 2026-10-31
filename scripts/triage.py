#!/usr/bin/env python3
"""Title triage: the run looks at company and title only, drops what is plainly not his field,
and reads the rest in full.

Added 29 Sep 2026 at the candidate's request. That morning the run read 52 of 477 candidates, and an
audit of the unread 404 found 34 jobs worth sending. A title pass on the same 404 dropped 136 rows
(radiologist postings, student and thesis roles, sales, project managers, technicians) and only
one useful row among them, a borderline annotation role.

    python3 scripts/triage.py $SC list            write $SC/titles.txt, one numbered line per candidate
    python3 scripts/triage.py $SC apply           remove the rows listed in $SC/title_drop.txt

title_drop.txt: one row per line, "<number> <reason>", or just numbers separated by spaces or
commas. Removed rows go to $SC/title_dropped.json with the reason, so the drop can be audited.
apply refuses to remove more than MAX_SHARE of the candidates unless --force is given, because
a wrong list of numbers must not empty the run.

What to drop: a title that is plainly not AI, ML, computer vision, data science, MLOps, agentic,
LLM, GenAI, NLP, speech or audio ML, or robotics perception work. What to keep: anything related,
and every unclear title ("Software Engineer II", "Member of Technical Staff", a recruiter's generic
"Engineer", "Research Engineer" with no field). When in doubt, keep.
"""
import json
import os
import re
import sys

MAX_SHARE = 0.7


def _load(sc):
    return json.load(open(os.path.join(sc, "candidates.json"), encoding="utf-8"))


def listing(sc):
    rows = _load(sc)
    lines = ["%d | %s | %s | %s | %s" % (i + 1, r.get("prescore", ""), (r.get("company") or "")[:40],
                                       (r.get("title") or "")[:110], (r.get("source") or "")[:18])
             for i, r in enumerate(rows)]
    out = os.path.join(sc, "titles.txt")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return out, len(rows)


def parse(text, n):
    """{row number: reason} from title_drop.txt. Numbers outside 1..n are ignored."""
    picked = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(\d+)\s*[:|\-]?\s*([A-Za-z].*)?$", line)
        if m and (m.group(2) or "").strip():
            k = int(m.group(1))
            if 1 <= k <= n:
                picked[k] = m.group(2).strip()[:60]
            continue
        for tok in re.findall(r"\d+", line):
            k = int(tok)
            if 1 <= k <= n:
                picked.setdefault(k, "")
    return picked


def apply(sc, force=False):
    rows = _load(sc)
    path = os.path.join(sc, "title_drop.txt")
    if not os.path.exists(path):
        return None, "no title_drop.txt, nothing removed"
    picked = parse(open(path, encoding="utf-8").read(), len(rows))
    if len(picked) > MAX_SHARE * len(rows) and not force:
        return None, "refused: %d of %d rows (over %d%%); check the numbers or pass --force" % (
            len(picked), len(rows), int(MAX_SHARE * 100))
    kept = [r for i, r in enumerate(rows) if i + 1 not in picked]
    dropped = [dict(row=i + 1, company=r.get("company"), title=r.get("title"), source=r.get("source"),
                    reason=picked[i + 1]) for i, r in enumerate(rows) if i + 1 in picked]
    json.dump(kept, open(os.path.join(sc, "candidates.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(dropped, open(os.path.join(sc, "title_dropped.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return len(dropped), "title triage: %d dropped, %d left to read (title_dropped.json)" % (len(dropped), len(kept))


if __name__ == "__main__":
    sc, cmd = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "list")
    if cmd == "list":
        out, n = listing(sc)
        print("%d candidates listed in %s" % (n, out))
    elif cmd == "apply":
        n, msg = apply(sc, force="--force" in sys.argv)
        print(msg)
        sys.exit(0 if n is not None or msg.startswith("no title_drop") else 1)
    else:
        sys.exit("usage: triage.py <scratch> list|apply [--force]")
