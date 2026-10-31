#!/usr/bin/env python3
"""Safe git sync for this repo, from the laptop and from the cloud runs.

Three things write to this repo: the laptop session, the three daily radar runs,
and the weekly email workflow. So a pull can land on a dirty tree and a push can
lose a race, and both used to fail in a way that needed hands:

  - `git pull --ff-only` aborts with "cannot pull with rebase: You have unstaged
    changes" whenever the company cache has laptop edits, which is most of the
    time. `pick.py` then pushed anyway, from a branch that was behind, and the
    push was rejected.
  - two runs pushing close together reject the second one. `deliver.yml` already
    carried its own retry loop for exactly this.

    gitsync.py pull                     stash, rebase, restore
    gitsync.py push companies -m "..."  add, commit, push, rebase and retry
    gitsync.py sync companies -m "..."  both, in that order

Nothing here throws work away. If the stash cannot be restored cleanly it stops,
leaves the stash in place, names it, and exits non-zero. A conflict is a thing to
look at, never a thing to resolve by picking a side.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STASH_TAG = "gitsync auto"
TRIES = 4


def git(*args, check=False, quiet=True):
    p = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if p.returncode and not quiet:
        print(f"  ! git {' '.join(args)} -> {(p.stderr or p.stdout).strip()[:300]}", file=sys.stderr)
    if p.returncode and check:
        raise SystemExit(f"gitsync: git {' '.join(args)} failed: {(p.stderr or p.stdout).strip()[:300]}")
    return p


def dirty():
    """Tracked changes or untracked files. Untracked counts: an untracked file
    that also arrives in the pull collides and stops the rebase."""
    return bool(git("status", "--porcelain").stdout.strip())


def stash_push():
    """Returns True only if a stash was actually created."""
    before = git("stash", "list").stdout
    git("stash", "push", "-u", "-m", STASH_TAG, quiet=False)
    after = git("stash", "list").stdout
    return after != before


def stash_pop():
    p = git("stash", "pop")
    if p.returncode:
        ref = git("stash", "list").stdout.splitlines()
        ref = ref[0].split(":")[0] if ref else "stash@{0}"
        print(
            f"gitsync: your changes could not be restored on top of the pull.\n"
            f"  They are safe in {ref}. Nothing was discarded.\n"
            f"  Look at it with: git -C {REPO} stash show -p {ref}\n"
            f"  Then: git -C {REPO} stash pop   and resolve the conflict.",
            file=sys.stderr,
        )
        return False
    return True


def pull():
    """Rebase onto origin/main, carrying local edits across."""
    git("fetch", "-q", "origin", "main", quiet=False)
    stashed = stash_push() if dirty() else False
    p = git("pull", "-q", "--rebase", "origin", "main")
    if p.returncode:
        # A failed rebase leaves the tree mid-rebase. Back out so the stash can
        # go home, rather than stacking a conflict on a conflict.
        git("rebase", "--abort")
        print(
            f"gitsync: rebase onto origin/main failed: "
            f"{(p.stderr or p.stdout).strip()[:300]}",
            file=sys.stderr,
        )
        if stashed:
            stash_pop()
        return False
    if stashed and not stash_pop():
        return False
    print(f"gitsync: pulled, now at {git('rev-parse', '--short', 'HEAD').stdout.strip()}")
    push_stranded()
    return True


SYNC_PREFIX = "Sync from the laptop"


def push_stranded():
    """Push commits that a failed push left behind on the laptop (docs/PROBLEMS.md 8.1).

    On 2 Oct 2026 `pick.py applied` committed at 15:03 and its push failed on a GitHub access error.
    Nothing tried again: the half-hourly pull reported "up to date" for four hours, the evening run
    then added its own row for the same application, and every pull after that stopped on the
    conflict. Now each pull pushes what is still local, when every such commit is one of pick.py's
    own ("Sync from the laptop: ..."). Anything else is left alone and named, so work in progress on
    main is never pushed by a timer. The line starts with UNPUSHED so the log can be searched for it."""
    ahead = git("log", "--format=%s", "origin/main..HEAD").stdout.strip().splitlines()
    if not ahead:
        return True
    if not all(s.startswith(SYNC_PREFIX) for s in ahead):
        print(f"gitsync: UNPUSHED: {len(ahead)} local commits on main, not all made by pick.py. Push them by hand.",
              file=sys.stderr)
        return False
    p = git("push", "-q", "origin", "HEAD:main")
    if p.returncode:
        print(f"gitsync: UNPUSHED: {len(ahead)} commits from pick.py are still only on this laptop "
              f"({(p.stderr or p.stdout).strip()[:120]}). The next pull tries again.", file=sys.stderr)
        return False
    print(f"gitsync: pushed {len(ahead)} commits from pick.py that had not reached GitHub")
    return True


def push(paths, message):
    if not paths:
        paths = ["-A"]
    git("add", *paths, quiet=False)
    if not git("diff", "--cached", "--quiet").returncode:
        print("gitsync: nothing staged, nothing to push")
        return True
    git("commit", "-q", "-m", message, check=True)
    for i in range(1, TRIES + 1):
        if git("push", "-q", "origin", "HEAD:main").returncode == 0:
            print(f"gitsync: pushed {git('rev-parse', '--short', 'HEAD').stdout.strip()}")
            return True
        print(f"gitsync: push rejected, rebasing and retrying ({i}/{TRIES})", file=sys.stderr)
        if git("pull", "-q", "--rebase", "origin", "main").returncode:
            git("rebase", "--abort")
            print(
                "gitsync: could not rebase onto origin/main. Your commit is made "
                "but not pushed; it is not lost. Resolve by hand.",
                file=sys.stderr,
            )
            return False
        time.sleep(i * 2)
    print("gitsync: push still rejected after retries. The commit is local and safe.", file=sys.stderr)
    return False


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pull")
    for name in ("push", "sync"):
        s = sub.add_parser(name)
        s.add_argument("paths", nargs="*", help="paths to stage, default is everything")
        # -A is what a hand reaches for, so accept it rather than erroring out on it.
        # With no paths the effect is the same.
        s.add_argument("-A", "--all", action="store_true", help="stage everything, the default")
        s.add_argument("-m", "--message", required=True)
    args = p.parse_args()

    if args.cmd == "pull":
        return 0 if pull() else 1
    paths = [] if getattr(args, "all", False) else args.paths
    if args.cmd == "push":
        return 0 if push(paths, args.message) else 1
    if args.cmd == "sync":
        if not pull():
            return 1
        return 0 if push(paths, args.message) else 1


if __name__ == "__main__":
    sys.exit(main())
