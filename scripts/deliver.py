#!/usr/bin/env python3
"""What a run delivers: the part of the shortlist above the cut, as the body of a GitHub issue.

Added 1 Nov 2026 in place of Gmail. The queue the person reads is the repository's open issues
with the `shortlist` label: one issue per run, opened by .github/workflows/deliver.yml with the
Action's own token, so no secret is needed. GitHub notifies the person the way they already
chose for the repository. Closing the issue is how a run is marked read. scripts/queue.py lists,
shows and closes them from a laptop. Email over Gmail (scripts/send_mail.py) still works when
the two secrets are set, as an extra, never as the only path.

    python3 scripts/deliver.py [--raw] <shortlist.md> [--out <body file>]

Prints the issue title on stdout, or SKIP for a noon run with nothing in it. Writes the body to
`--out` when given, else to stdout after the title. --raw keeps the whole file (a correction).
"""
import json
import re
import sys
from pathlib import Path

CUT = re.compile(r"^\s{0,3}#{1,6}\s+(?:Run details|Rejected)\b.*$", re.M | re.I)
RULES = re.compile(r"(?:^\s*(?:-{3,}|\*{3,}|_{3,})\s*$\s*)+\Z", re.M)


def title_for(path, body):
    first = body.lstrip().splitlines()[0] if body.strip() else ""
    if first.startswith("#"):
        return first.lstrip("#").strip()
    return "Job radar, %s" % Path(path).stem


def empty_noon(path):
    """True for a noon shortlist with nothing in it: no job, no fit-6 line, no borderline line."""
    try:
        d = json.loads(Path(str(path)[:-3] + ".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return d.get("slot") == "noon" and not any(d.get(k) for k in ("jobs", "also_found", "borderline"))


def body_for(path, raw=False):
    """The text to deliver, or None when nothing should go out.

    Everything from "Run details" down stays in the file (write_pack.py, docs/PROBLEMS.md 6.1); older
    files have no such heading and are cut at "Rejected". Any heading level counts: a run that wrote
    "# Rejected" once delivered its whole rejection audit (28 Aug 2026, 11 of 17 runs). A correction
    (--raw) keeps the whole file, since its Rejections section is the point."""
    body = Path(path).read_text(encoding="utf-8")
    if not raw:
        if empty_noon(path):
            return None
        body = CUT.split(body)[0]
        body = RULES.sub("", body)
    return body.rstrip()


def main(argv):
    raw = "--raw" in argv
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    paths = [a for i, a in enumerate(argv) if a not in ("--raw", "--out") and (i == 0 or argv[i - 1] != "--out")]
    if not paths:
        print("usage: deliver.py [--raw] <shortlist.md> [--out <file>]", file=sys.stderr)
        return 2
    path = paths[0]
    body = body_for(path, raw)
    if body is None:
        print("SKIP")
        return 0
    print(title_for(path, body))
    if out:
        Path(out).write_text(body + "\n", encoding="utf-8")
    else:
        print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
