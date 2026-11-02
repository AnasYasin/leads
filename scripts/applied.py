#!/usr/bin/env python3
"""Mark a job applied, from any session in this repository. No laptop needed.

    python3 scripts/applied.py "<company>" "<role>" [--cv CV_LLM] [--date YYYY-MM-DD] [--no-push]

Stamps the row in state/applications.md (or adds one), commits and pushes. The next run skips
that role, and the store (scripts/store.py) shows the job as applied with the CV named.
"""
import datetime
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pipeline  # noqa: E402


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    company, role = args[0], args[1]
    day = argv[argv.index("--date") + 1] if "--date" in argv else datetime.date.today().isoformat()
    cv = argv[argv.index("--cv") + 1] if "--cv" in argv else ""
    msg = pipeline.log_application(company, role, day, how="by hand", docs=cv)
    print(msg)
    if "NOT written" in msg or "already says" in msg:
        return 1
    if "--no-push" not in argv:
        subprocess.run([sys.executable, os.path.join(HERE, "gitsync.py"), "push", "-A", "-m",
                        "Applied: %s, %s" % (company, role)], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
