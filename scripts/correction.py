#!/usr/bin/env python3
"""Was this shortlist already emailed? If so, write a short correction email instead.

Added 29 Sep 2026. That morning's run pushed "7 new", then re-rendered and pushed "9 new
(corrected)" four minutes later, and deliver.yml emailed the whole list twice. A shortlist file
that already existed in an earlier commit has been emailed before, so the second push only needs
to say what changed.

    python3 scripts/correction.py shortlists/2026-09-29-morning.md

Prints the path of a correction email (markdown) when the file was committed before this push,
and prints nothing when this is the first version. deliver.yml mails the correction when there
is one and the full shortlist otherwise.
"""
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def jobs(data):
    rows = data.get("jobs") if isinstance(data, dict) else None
    return [j for j in rows or [] if isinstance(j, dict)]


def key(j):
    return ("%s | %s" % (j.get("company", ""), j.get("title", ""))).strip()


def main(md_path, out_dir=None):
    rel = os.path.relpath(os.path.abspath(md_path), REPO)
    js = rel[:-3] + ".json"
    # Commits that touched the shortlist, newest first. HEAD is this push.
    hist = git("log", "--format=%H", "--", rel).stdout.split()
    if len(hist) < 2:
        return None
    prev = git("show", "%s:%s" % (hist[1], js))
    if prev.returncode:
        return None
    try:
        old = jobs(json.loads(prev.stdout))
        new = jobs(json.load(open(os.path.join(REPO, js), encoding="utf-8")))
    except Exception:
        return None
    ok, nk = {key(j) for j in old}, {key(j) for j in new}
    added = [j for j in new if key(j) not in ok]
    removed = [j for j in old if key(j) not in nk]
    stem = os.path.basename(rel)[:-3]
    lines = ["# Correction: Job radar, %s, now %d jobs" % (stem, len(new)), "",
             "This run was already emailed. It was rendered again afterwards. Only the changes are below;",
             "the full list is in shortlists/%s.md and in reports/LATEST.md." % stem, ""]
    if added:
        lines += ["## Added (%d)" % len(added), ""]
        for j in added:
            lines.append("- **%s — %s** · %s · fit %s · %s" % (j.get("title", ""), j.get("company", ""),
                         j.get("location", ""), j.get("fit", "?"), j.get("apply_url", "")))
        lines.append("")
    if removed:
        lines += ["## Removed (%d)" % len(removed), ""]
        for j in removed:
            lines.append("- %s — %s" % (j.get("title", ""), j.get("company", "")))
        lines.append("")
    if not added and not removed:
        lines += ["The job list did not change; only the text around it was edited.", ""]
    out = os.path.join(out_dir or os.environ.get("RUNNER_TEMP") or "/tmp", "correction-%s.md" % stem)
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    return out


if __name__ == "__main__":
    p = main(sys.argv[1])
    if p:
        print(p)
