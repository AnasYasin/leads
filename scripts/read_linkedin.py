#!/usr/bin/env python3
"""Full descriptions for LinkedIn candidates, through the guest job-posting endpoint.

    https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/<li_id>

Verified 8 Sep 2026. Returns the whole description (6,000+ characters on the first job
tried), the criteria block (seniority level, employment type, job function, industry),
the company's LinkedIn page, and a "posted N hours ago" line. There is no external
apply link in the guest page, so the canonical url has to be found on the employer's
own board as in instructions/PROMPT.md section 3, with the LinkedIn url as the fallback.

Usage: read_linkedin.py <scratchdir> [<substring> ...]
Reads candidates.json, takes rows with source "linkedin", optionally filtered by
"company | title" substring, writes linkedin_read.json and prints one block per job.
"""
import json
import os
import re
import sys
import time
import urllib.request
import concurrent.futures as cf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lang_band import band as lang_band
from trim_desc import trim
from textclean import html_to_text

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9,de;q=0.8"}

# 29 Sep 2026: importable, so scripts/fetch_desc.py can reuse one() without the command line.
needles = []


def one(j):
    key = ("%s | %s" % (j.get("company", ""), j.get("title", ""))).lower()
    if needles and not any(n in key for n in needles):
        return None
    out = dict(j)
    url = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/%s" % j["li_id"]
    for attempt in range(2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
                t = r.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                time.sleep(15)
                continue
            out["error"] = "HTTP %d" % e.code
            return out
        except Exception as e:
            out["error"] = str(e)[:80]
            return out
    d = re.search(r'description__text[^>]*>(.*?)</div>\s*</div>', t, re.S)
    out["desc"] = html_to_text(d.group(1)) if d else ""      # whole text, no cut (2 Oct 2026)
    org = re.search(r'topcard__org-name-link[^>]*href="([^"?]+)', t)
    out["company_linkedin"] = org.group(1) if org else ""
    out["criteria"] = dict(re.findall(
        r'description__job-criteria-subheader">\s*(.*?)\s*<.*?description__job-criteria-text[^>]*>\s*(.*?)\s*<',
        t, re.S))
    ago = re.search(r'posted-time-ago__text[^>]*>\s*(.*?)\s*<', t, re.S)
    out["posted_ago"] = ago.group(1).strip() if ago else ""
    out["band"], out["lang_line"] = lang_band(out["desc"])
    return out


if __name__ == "__main__":
    scratch = sys.argv[1]
    needles = [n.lower() for n in sys.argv[2:]]
    cands = json.load(open(os.path.join(scratch, "candidates.json")))
    rows = [c for c in cands if c.get("source") == "linkedin"]
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        done = [r for r in ex.map(one, rows) if r]
    json.dump(done, open(os.path.join(scratch, "linkedin_read.json"), "w"), ensure_ascii=False, indent=1)

    for j in done:
        print("=" * 100)
        print("%s | %s\nloc=%s date=%s posted=%s src=linkedin band=%s\nurl=%s\ncompany_linkedin=%s\ncriteria=%s\nLANG: %s"
              % (j.get("company"), j.get("title"), j.get("location"), j.get("date"),
                 j.get("posted_ago"), j.get("band"), j.get("url"), j.get("company_linkedin"),
                 j.get("criteria"), j.get("lang_line")))
        if j.get("error"):
            print("ERROR", j["error"])
        # 29 Sep 2026: benefits and boilerplate trimmed from the printout; linkedin_read.json keeps the full text.
        print(trim(j.get("desc", ""))[0])
    print("%d LinkedIn jobs read, %d errors" % (len(done), sum(1 for j in done if j.get("error"))),
          file=sys.stderr)
