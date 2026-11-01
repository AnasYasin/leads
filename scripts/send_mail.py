#!/usr/bin/env python3
"""Email one shortlist file over Gmail SMTP. Optional since 1 Nov 2026: the queue is the GitHub
issue deliver.yml opens (scripts/deliver.py); this runs only when the two secrets are set.

Credentials come from the GMAIL_ADDRESS and GMAIL_APP_PASSWORD repository
secrets. A normal Google password will not work, it has to be an app password.
"""

import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deliver import body_for, empty_noon, title_for  # noqa: E402, F401  (one cut rule for the issue and the email)


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

    body = body_for(path, raw)
    if body is None:
        print(f"not sent: {path} is a noon run with no job to send, no fit-6 line and no borderline line")
        return 0

    msg = EmailMessage()
    msg["Subject"] = title_for(path, body)
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
