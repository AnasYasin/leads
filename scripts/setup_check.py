#!/usr/bin/env python3
"""Is the repository set up for a person? Run after SETUP.md, until it prints READY.

    python3 scripts/setup_check.py

Lists every `<fill: ...>` marker still in instructions/PROFILE.md, the empty values under `profile`
and `search` in config/radar.yaml, and the salary ask table when all four figures are empty. Exits 1
while anything is open. The profile path can be overridden with RADAR_PROFILE and the config with
RADAR_CONFIG (the tests do that).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cfg  # noqa: E402
import salary  # noqa: E402

ROOT = os.path.dirname(HERE)
LISTS = {"linkedin": ("roles", "places"), "bundesagentur": ("queries", "places"), "xing": ("queries", "places"),
         "stepstone": ("roles", "cities"), "talent": ("roles", "cities"), "getro": ("collections",)}


def problems(profile_path=None, config=None):
    out = []
    p = profile_path or os.environ.get("RADAR_PROFILE") or os.path.join(ROOT, "instructions", "PROFILE.md")
    text = open(p, encoding="utf-8").read()
    for m in re.finditer(r"<fill:?\s*([^>]{0,60})", text):
        out.append("PROFILE.md still has a blank: <fill: %s...>" % m.group(1).strip()[:50])
    c = config if config is not None else cfg.load()
    prof = c.get("profile") or {}
    if not str(prof.get("name") or "").strip():
        out.append("config/radar.yaml profile.name is empty")
    search = c.get("search") or {}
    for site, keys in LISTS.items():
        for k in keys:
            if not (search.get(site) or {}).get(k):
                out.append("config/radar.yaml search.%s.%s is empty" % (site, k))
    if not any(fig for fig, _ in (salary.ASK.get(k, ("", "")) for k in ("startup", "mid", "large", "public"))):
        out.append("scripts/salary.py ASK has no figure in any class (fine only if the person wants no ask line)")
    return out


def main():
    out = problems()
    for line in out:
        print(line)
    print("READY" if not out else "%d open" % len(out))
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main())
