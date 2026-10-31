#!/usr/bin/env python3
"""Text for a row the fetch could not read, from a link found by hand.

Added 29 Oct 2026. The noon run's whole pool had become rows without text: 10 rows, 8 of them on the
list since 3 to 18 Oct, retried every noon and listed under "Could not be read" in every mailed run.
A web search on 29 Oct found a readable copy for 2 of the 10 (Hornetsecurity on the Bundesagentur);
the other 8 were closed, outside Germany, or nowhere on the web.

    python3 scripts/retext.py $SC                 list every candidate without text: id, company, title, link, why
    python3 scripts/retext.py $SC <id> <url>      fetch the posting from <url> onto that row

On success the row gets the text and the new link (the old one stays in `url_card`), leaves
no_text.json, and read_next.py prints it in the next batch like any other job. On failure nothing
changes and the reason is printed. A row that no link can resolve is retired with a verdict of gate
`no_text` (scripts/verdict.py), which needs no printed text.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import read_next as R  # noqa: E402


def fetch(row, url):
    """The row with its text, through the reader that knows the link's site."""
    m = re.search(r"arbeitsagentur\.de/jobsuche/jobdetail/([^/?#]+)", url)
    if m:
        import read_jobs
        return read_jobs.one(dict(row, source="Bundesagentur", ref=m.group(1), url=url))
    m = re.search(r"linkedin\.com/jobs/view/(?:[^/?#]*-)?(\d+)", url)
    if m:
        import read_linkedin
        return read_linkedin.one(dict(row, li_id=m.group(1), url=url))
    import jobpage
    return jobpage.one(dict(row, url=url, apply_url="", externe_url=""))


def textless(sc):
    why = {}
    for n in R._load(os.path.join(sc, "no_text.json"), []):
        why[n.get("url")] = n.get("why", "")
    return [(j, why.get(j.get("url"), "")) for j in R.candidates(sc) if not R.has_text(j)]


def apply(sc, cid, url, fetch=fetch):
    """Returns (ok, message)."""
    rows = R.candidates(sc)
    i = next((k for k, j in enumerate(rows) if R.cid(j) == cid), None)
    if i is None:
        return False, "%s: not in candidates.json" % cid
    r = fetch(rows[i], url) or {}
    desc = "" if r.get("error") or r.get("err") else (r.get("desc") or "")
    if desc.startswith("FETCH FAILED") or len(desc) < R.THIN:
        return False, "%s: no text from %s (%s)" % (cid, url, r.get("error") or r.get("err") or "%d characters" % len(desc))
    rows[i] = dict(rows[i], url_card=rows[i].get("url"), url=url, desc=desc, desc_src=r.get("desc_src") or "retext",
                   desc_len=len(desc), retext=True)
    json.dump(rows, open(os.path.join(sc, "candidates.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    p = os.path.join(sc, "no_text.json")
    if os.path.exists(p):
        old = rows[i]["url_card"]
        json.dump([n for n in R._load(p, []) if n.get("url") != old], open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return True, "%s: %d characters from %s. It is in the next batch." % (cid, len(desc), url)


def main(argv):
    if len(argv) == 1:
        rows = textless(argv[0])
        for j, w in rows:
            print("%s | %s | %s | %s | %s" % (R.cid(j), j.get("company"), j.get("title"), j.get("url"), w))
        print("%d candidates without text" % len(rows))
        return 0
    if len(argv) != 3:
        print(__doc__)
        return 2
    ok, msg = apply(*argv)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
