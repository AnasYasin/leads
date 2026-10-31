#!/usr/bin/env python3
"""Email one shortlist file over Gmail SMTP.

Credentials come from the GMAIL_ADDRESS and GMAIL_APP_PASSWORD repository
secrets. A normal Google password will not work, it has to be an app password.
"""

import os
import re
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path


def subject_for(path, body):
    first = body.lstrip().splitlines()[0] if body.strip() else ""
    if first.startswith("#"):
        return first.lstrip("#").strip()
    stem = Path(path).stem
    return f"Job radar, {stem}"


def empty_noon(path):
    """True for a noon shortlist that has nothing for him: no job, no fit-6 line, no borderline line."""
    import json
    try:
        d = json.loads(Path(str(path)[:-3] + ".json").read_text())
    except (OSError, ValueError):
        return False
    return d.get("slot") == "noon" and not any(d.get(k) for k in ("jobs", "also_found", "borderline"))


def main():
    argv = [a for a in sys.argv[1:] if a != "--raw"]
    # The shortlist carries a Rejected section that is stripped below. The weekly
    # pipeline digest has a Rejections section that must survive, so it is mailed
    # with --raw. Without this the digest would be cut off at that heading and the
    # interviews and open applications under it would never arrive.
    raw = "--raw" in sys.argv[1:]
    if not argv:
        print("usage: send_mail.py [--raw] <path>", file=sys.stderr)
        return 2

    path = Path(argv[0])
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 1

    address = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not address or not password:
        print("GMAIL_ADDRESS or GMAIL_APP_PASSWORD is not set", file=sys.stderr)
        return 1

    body = path.read_text()

    # The rejected section is for auditing the scoring later, not for the inbox.
    #
    # This pattern used to require exactly two hashes, and that silently failed open:
    # a run that wrote "# Rejected" instead of "## Rejected" mailed its entire rejection
    # audit to the candidate. Checked on 28 August 2026 evening, **11 of the previous 17 runs did
    # exactly that**, roughly doubling the length of those emails. The heading level is
    # incidental formatting, so match any of them, tolerate trailing punctuation and
    # case, and strip any horizontal rules left dangling above the split point.
    if not raw:
        # 2 Oct 2026: the noon run found 0 jobs on 1 Oct and 1 on 2 Oct and mailed both. A noon run with
        # nothing to show sends nothing (the candidate). The file is still written and reports/LATEST.md still rolls.
        if empty_noon(path):
            print(f"not sent: {path} is a noon run with no job to send, no fit-6 line and no borderline line")
            return 0
        # Everything from "Run details" down is kept in the file and left out of the email
        # (write_pack.py, docs/PROBLEMS.md 6.1). Older files have no such heading and are cut at "Rejected".
        body = re.split(r"^\s{0,3}#{1,6}\s+(?:Run details|Rejected)\b.*$", body, flags=re.M | re.I)[0]
        body = re.sub(r"(?:^\s*(?:-{3,}|\*{3,}|_{3,})\s*$\s*)+\Z", "", body, flags=re.M)
    body = body.rstrip()

    msg = EmailMessage()
    msg["Subject"] = subject_for(path, body)
    msg["From"] = address
    msg["To"] = address
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(address, password)
        smtp.send_message(msg)

    print(f"sent {path} to {address}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
