#!/usr/bin/env python3
"""Is this job still up? One line per url, exit code 0 when all are live.

Used twice. The cloud run calls it on the final shortlist right before writing, so a job
that vanished between collection and sending is caught (7 of 8 Bundesagentur jobs sent on
28 July 2026 were gone by 8 September). the candidate's laptop calls it from `pick.py` before he
opens a job, because a dead link costs him a captcha and a wasted click.

Checks by url shape:
  arbeitsagentur.de/jobsuche/jobdetail/<ref>   -> v4 jobdetails API, 404 means gone
  linkedin.com/jobs/view/...-<id>              -> guest jobPosting endpoint, must carry a description
  xing.com/jobs/...-<id>                       -> job page must still carry "activatedAt"; a 410 is UNSURE
                                                  (XING sends 410 for region blocks as well as deletions)
  jobs.ashbyhq.com/<slug>/<uuid>               -> Ashby posting API for the board must list the uuid (the page is a SPA shell, 200 for anything)
  boards.greenhouse.io, jobs.lever.co, *.jobs.personio.*, join.com, recruitee,
  workable, smartrecruiters, teamtailor         -> plain GET, 200 and no "no longer"/"expired" text
  anything else                                 -> plain GET, 200 and no "no longer"/"expired" text

Output: LIVE | GONE | UNSURE, then the reason, then the url.
Usage: check_live.py <url> [<url> ...]      or     check_live.py - (urls on stdin)
"""
import base64
import re
import sys
import urllib.request
import urllib.error

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9,de;q=0.8"}
BA = dict(UA, **{"X-API-Key": "jobboerse-jobsuche"})
GONE_TEXT = re.compile(
    r"no longer (available|accepting|open|active)|this job has expired|job (is )?closed|"
    r"position (has been )?filled|nicht mehr verf(ü|ue)gbar|stellenangebot (ist )?(nicht mehr|abgelaufen)|"
    r"diese stelle (ist|wurde) (bereits )?(besetzt|geschlossen|deaktiviert)|"
    r"job not found|posting (has been )?removed|sorry, this job", re.I)


def get(url, hdr=UA, cap=400000):
    req = urllib.request.Request(url, headers=hdr)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.status, r.read(cap).decode("utf-8", "replace")


def check(url):
    u = url.strip()
    try:
        if "arbeitsagentur.de/jobsuche/jobdetail/" in u:
            ref = u.rstrip("/").split("/")[-1].split("?")[0]
            api = ("https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/"
                   + base64.b64encode(ref.encode()).decode())
            try:
                get(api, BA)
                return "LIVE", "BA API 200"
            except urllib.error.HTTPError as e:
                return ("GONE", "BA API 404") if e.code == 404 else ("UNSURE", "BA API %d" % e.code)
        m = re.search(r"linkedin\.com/jobs/view/(?:.*-)?(\d{6,})", u)
        if m:
            try:
                st, body = get("https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/" + m.group(1))
            except urllib.error.HTTPError as e:
                return ("GONE", "LinkedIn %d" % e.code) if e.code == 404 else ("UNSURE", "LinkedIn %d" % e.code)
            if "description__text" in body:
                return "LIVE", "LinkedIn guest page has description"
            return "GONE", "LinkedIn guest page without description"
        # jobs.ashbyhq.com is a SPA shell that answers 200 for any slug and any job id, so a
        # plain GET proves nothing (instructions/COMPANIES.md, 3 Aug 2026 note). Ask the posting API for the
        # board and look for the job id in it.
        m = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{36})", u)
        if m:
            try:
                # Read the whole board: Pennylane's is 4.3 MB and the job id sat at offset
                # 4.27 MB, so the default 400 KB cap reported a false GONE (9 Sep 2026).
                st, body = get("https://api.ashbyhq.com/posting-api/job-board/" + m.group(1),
                               cap=32000000)
            except urllib.error.HTTPError as e:
                return ("GONE", "Ashby board 404") if e.code == 404 else ("UNSURE", "Ashby API %d" % e.code)
            return ("LIVE", "Ashby API lists the job") if m.group(2) in body else ("GONE", "Ashby API does not list the job")
        st, body = get(u)
        if st != 200:
            return "UNSURE", "HTTP %d" % st
        if "xing.com/jobs/" in u:
            return ("LIVE", "XING activatedAt present") if '"activatedAt"' in body else ("GONE", "XING page without job state")
        # talent.com ships its whole i18n string table inside the page as escaped JSON, so
        # every row carries "Dieses Stellenangebot ist abgelaufen oder nicht mehr verfügbar"
        # whether or not it applies. Drop escaped-JSON strings before matching (10 Sep 2026).
        body = re.sub(r'\\"[^"]*?\\"', " ", body) if "talent.com/view" in u else body
        # Same trap on every SPA that bundles its translations into the page, not just
        # talent.com: join.com carries "Diese Stelle ist nicht mehr verfügbar" as the
        # jobApply.jobAd.archivedJob.title string and Recruitee carries "no longer active"
        # as an expired-job-alert-link string, so both reported a false GONE on live jobs
        # (WeSort.AI and Machine Learning Reply, 14 Sep 2026). Those tables live in <script>
        # blocks while a real closed-notice is rendered markup, so drop scripts first.
        body = re.sub(r"(?is)<script\b.*?</script>", " ", body)
        # Recruitee ships the same table entity-escaped inside an attribute rather than in a
        # script, so also drop &quot;-quoted JSON strings the way the talent.com line above
        # drops backslash-quoted ones.
        body = re.sub(r"&quot;[^<]*?&quot;", " ", body)
        if GONE_TEXT.search(body):
            return "GONE", "page says: " + GONE_TEXT.search(body).group(0)
        return "LIVE", "HTTP 200"
    except urllib.error.HTTPError as e:
        # XING answers 410 with an empty body both for a deleted advert and for a regional
        # block (pHera, 8 Sep 2026: 410 from the laptop, LIVE from the cloud an hour earlier).
        # So a XING 410 is UNSURE, and only a 410 with a real "gone" body counts as GONE.
        if "xing.com/jobs/" in u and e.code == 410:
            return "UNSURE", "XING 410, deleted or region-blocked, open it in a browser"
        if e.code == 410:
            try:
                body = e.read(200000).decode("utf-8", "replace")
            except Exception:
                body = ""
            return ("GONE", "HTTP 410") if (len(body) < 50 or GONE_TEXT.search(body)) else ("UNSURE", "HTTP 410 with a full page")
        return ("GONE", "HTTP 404") if e.code == 404 else ("UNSURE", "HTTP %d" % e.code)
    except Exception as e:
        return "UNSURE", str(e)[:60]


def main():
    urls = sys.argv[1:]
    if urls == ["-"] or not urls:
        urls = [l for l in sys.stdin.read().splitlines() if l.strip()]
    bad = 0
    for u in urls:
        status, why = check(u)
        bad += status != "LIVE"
        print("%-6s %-40s %s" % (status, why, u))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
