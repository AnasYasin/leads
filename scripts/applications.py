"""One reader for state/applications.md.

The file is a markdown table, one row per job researched, written on the laptop by pick.py
and on the cloud by pipeline.py. Before 1 Nov 2026 five scripts parsed it with their own
split-on-pipe and their own column numbers; this is the one place that knows the columns.

    | Researched | Company | Role | Location | Verdict | Docs built | Applied | Outcome |

rows(path)        every dated row as a dict with the COLS keys, in file order
applied(path)     (company, role) for every row whose Applied cell starts with "yes"
older_names(path) the comma list under "## Older applications", raw
"""
import re

COLS = ["Researched", "Company", "Role", "Location", "Verdict", "Docs built", "Applied", "Outcome"]
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse(line):
    """One table line as a dict with the COLS keys, padded, or None when it is not a dated row."""
    if not line.startswith("|"):
        return None
    c = [x.strip() for x in line.strip().strip("|").split("|")]
    if not _DATE.match(c[0]):
        return None
    c += [""] * (len(COLS) - len(c))
    return dict(zip(COLS, c))


def line(row):
    """The table line for a row dict, the inverse of parse()."""
    return "| " + " | ".join(row.get(k, "").replace("|", "/") for k in COLS) + " |"


def _text(path):
    try:
        return open(path, encoding="utf-8").read()
    except OSError:
        return ""


def rows(path):
    return [r for r in (parse(l) for l in _text(path).splitlines()) if r]


def applied(path):
    return [(r["Company"], r["Role"]) for r in rows(path) if r["Applied"].lower().startswith("yes")]


def older_names(path):
    m = re.search(r"## Older applications.*?\n\n.*?\n\n(.*?)(?:\n\n|\Z)", _text(path), re.S)
    return [n.strip() for n in m.group(1).replace("\n", " ").split(",")] if m else []
