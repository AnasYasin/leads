#!/usr/bin/env python3
"""The shortlist queue from a laptop: the repository's open issues with the `shortlist` label.

    python3 scripts/inbox.py            list the unread runs, newest first
    python3 scripts/inbox.py <n>        print one run's shortlist
    python3 scripts/inbox.py done <n>   close it: the run is read

Needs the GitHub CLI (`gh`) logged in. The repository is the one this file lives in, read from
its git remote by gh. The same queue is the Issues tab on GitHub and the notifications GitHub
already sends for it.
"""
import json
import subprocess
import sys

LABEL = "shortlist"


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def unread():
    out = gh("issue", "list", "--label", LABEL, "--state", "open", "--limit", "50", "--json", "number,title,createdAt")
    return json.loads(out or "[]")


def main(argv):
    if not argv:
        rows = unread()
        for r in rows:
            print("%5d  %s  %s" % (r["number"], r["createdAt"][:10], r["title"]))
        print("%d unread" % len(rows))
        return 0
    if argv[0] == "done" and len(argv) > 1:
        gh("issue", "close", argv[1], "--comment", "read")
        print("closed #%s" % argv[1])
        return 0
    print(gh("issue", "view", argv[0], "--json", "body", "-q", ".body"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except subprocess.CalledProcessError as ex:
        print(ex.stderr.strip() or "gh failed", file=sys.stderr)
        sys.exit(1)
