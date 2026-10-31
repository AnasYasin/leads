#!/usr/bin/env python3
"""Rebuild reports/LATEST.md from the two most recent shortlists.

The newest run goes on top, the one before it underneath, and everything older
is left in shortlists/ but dropped from the file. Run this after the radar
pushes a new shortlist.

Prints the path of the newest shortlist on stdout so the workflow can mail it.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHORTLISTS = REPO / "shortlists"
LATEST = REPO / "reports/LATEST.md"

# Within a day the morning run comes first, so filenames cannot be sorted as
# plain strings. "evening" sorts before "morning" alphabetically.
SLOT_ORDER = {"morning": 0, "noon": 1, "evening": 2}
NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-(morning|noon|evening)\.md$")


def sort_key(path):
    m = NAME.match(path.name)
    return (m.group(1), SLOT_ORDER[m.group(2)])


def main():
    runs = sorted(
        (p for p in SHORTLISTS.glob("*.md") if NAME.match(p.name)),
        key=sort_key,
        reverse=True,
    )
    if not runs:
        print("no shortlists found", file=sys.stderr)
        return 1

    keep = runs[:2]
    parts = [
        "# Job radar, latest two runs",
        "",
        "Newest first. Older runs stay in `shortlists/` but drop out of this file.",
        "",
    ]
    for i, path in enumerate(keep):
        label = "Current run" if i == 0 else "Previous run"
        parts += [f"<!-- {path.name} -->", f"## {label} — {path.stem}", "", path.read_text().strip(), ""]
        if i == 0 and len(keep) > 1:
            parts += ["---", ""]

    LATEST.write_text("\n".join(parts) + "\n")
    print(keep[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
