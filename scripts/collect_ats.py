#!/usr/bin/env python3
"""Poll every ATS board in instructions/COMPANIES.md, including the documented exceptions."""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import concurrent.futures as cf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jobid import PLACE, fold
from textclean import html_to_text, join_html

# RADAR_KEEP_RAW=1 keeps each description's source HTML beside the cleaned text, as `desc_raw`,
# so a cleaning change can be compared with the old output on the same input. Off in a run.
KEEP_RAW = bool(os.environ.get("RADAR_KEEP_RAW"))

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{s}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{s}?mode=json",
    # Lever runs a separate EU instance and a slug on it 404s on the .co host. Finom's board
    # (`pnlfin`) lives there — found 5 Sep 2026 morning. Same JSON shape, so it reuses the
    # `lever` parser below; only the host differs.
    "lever_eu": "https://api.eu.lever.co/v0/postings/{s}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{s}?includeCompensation=true",
    "personio": "https://{s}.jobs.personio.de/xml",
    "teamtailor": "https://{s}.teamtailor.com/jobs.json",
    "teamtailor_feed": "https://{s}.teamtailor.com/jobs.json",
    # Teamtailor on a vanity host with no working <slug>.teamtailor.com. Slug is the full host.
    # SLNG, 10 Sep 2026: careers.slng.ai/jobs.json answers, slng.teamtailor.com 404s.
    "teamtailor_custom": "https://{s}/jobs.json",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{s}?details=true",
    "recruitee": "https://{s}.recruitee.com/api/offers/",
    "recruitee_custom": "https://{s}/api/offers/",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{s}/postings?limit=100",
    "personio_html": "https://{s}.jobs.personio.com/?language=en",
    "breezy": "https://{s}.breezy.hr/json",
    # Avature. No JSON feed exists, but unlike most enterprise ATSs the board is rendered
    # server-side, so the plain HTML with a browser UA IS the feed. Added 25 Aug 2026 for
    # DHL. Avature is common across large German employers, so this parser should port to
    # others by slug alone.
    "avature": "https://{s}.avature.net/en_US/careers/SearchJobs/",
    # Pinpoint. The board page itself is a JS shell, but postings.json next to it is the full
    # feed. Found 6 Aug 2026 evening on osapiens, whose careers.osapiens.com/postings/<uuid>
    # url shape is the giveaway for this ATS. `desc` is `description`; `requirements` is a
    # separate field and is often left unpublished, so a short description is not a parse bug.
    "pinpoint": "https://{s}/postings.json",
    # join.com. There IS a public REST endpoint at /api/public/companies/{s}/jobs, but its
    # `pageSize` validator rejected every integer tried (10, 12, 15, 20, 24, 25, 30, 50, 100)
    # while accepting `page=1`, so it is unusable without knowing the magic value. The board
    # page itself carries the whole list in the Next.js hydration payload — same trick as the
    # Getro `__NEXT_DATA__` method in instructions/PROMPT.md — under `initialState.jobs.items`, with a real
    # ISO `createdAt` per job. Found 24 Aug 2026 morning on datacept and kausableai.
    # Worth knowing: talent.com aged the Datacept role at "vor 3 Tagen" when `createdAt` said
    # it was 10 hours old. Trust the board's date over the aggregator's relative string.
    "join": "https://join.com/companies/{s}",
    # HireHive. The board page renders fine but `api/v1/jobs` next to it is the real feed:
    # full `description.html`, a `hostedUrl`, and epoch-second `publishedDate` / `createdDate`.
    # Found 8 Aug 2026 morning on luma-vision, reached from an Indeed search rather than a board
    # sweep. `/jobs.json` and `/api/jobs` both 404 here — only `/api/v1/jobs` answers.
    "hirehive": "https://{s}.hirehive.com/api/v1/jobs",
}

# instructions/COMPANIES.md is the one list of boards (1 Nov 2026; until then a second list lived here and
# the two had to be reconciled). Every line whose kind has a URL is polled.
def _from_companies_md(path=None):
    """Review, 29 Sep 2026: slugs may carry %20 ("Tools%20for%20Humanity"); the same board listed
    under two kinds of one ATS (teamtailor and teamtailor_feed, personio and personio_html,
    recruitee and recruitee_custom) is polled once, keyed on the ATS family and the company
    name; and a missing instructions/COMPANIES.md must not stop the whole collector."""
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instructions/COMPANIES.md")
    fam = lambda k: k.split("_")[0]
    nm = lambda n: fold(re.sub(r"\([^)]*\)", " ", n or ""))
    have, have_names, have_urls = set(), set(), set()
    out, dead = [], set()
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError as ex:
        print("instructions/COMPANIES.md not read: %s" % ex, file=sys.stderr)
        return out, dead
    for line in lines:
        m = re.match(r"\s*([a-z_]+)\s*\|\s*([A-Za-z0-9._%\-]+)\s*\|\s*(.+?)\s*\|", line)
        # 29 Oct 2026: a line whose kind is `dead` retires that slug everywhere.
        if m and m.group(1) == "dead":
            dead.add(m.group(2).lower())
            continue
        if not m or m.group(1) not in URLS:
            continue
        k, slug, name = m.group(1), m.group(2), m.group(3)
        url = URLS[k].format(s=slug)
        if (k, slug.lower()) in have or (fam(k), nm(name)) in have_names or url in have_urls:
            continue
        have.add((k, slug.lower()))
        have_names.add((fam(k), nm(name)))
        have_urls.add(url)
        out.append((k, slug, name))
    return [b for b in out if b[1].lower() not in dead], dead


BOARDS, DEAD = _from_companies_md()



def fetch(url, timeout=40, _retries=1):
    # 2 Oct 2026: a Personio board that is not public redirects to personio.com, and personio.com
    # answers a script with 429. That 429 was read as a rate limit on the board since 21 Aug 2026
    # (meshcapade, advastore), with a 20 second pause and a retry on every run. It is now reported
    # as what it is, and a real 429 from the board itself still gets one pause and retry.
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if "jobs.personio" in url and "jobs.personio" not in (getattr(e, "url", "") or url):
            raise RuntimeError("the board is not public, it redirects to %s" % e.url.split("//")[-1].strip("/")[:40])
        if e.code == 429 and _retries > 0:
            time.sleep(20)
            return fetch(url, timeout, _retries - 1)
        raise


def strip(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h or "", flags=re.S | re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    h = (h.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"'))
    return re.sub(r"\s+", " ", h).strip()


def _cdata(x):
    return re.sub(r"^\s*<!\[CDATA\[|\]\]>\s*$", "", x or "", flags=re.S)


def parse(kind, slug, name, raw):
    o = []
    if kind == "greenhouse":
        for j in json.loads(raw).get("jobs", []):
            o.append(dict(title=j.get("title", ""),
                          location=(j.get("location") or {}).get("name", ""),
                          # `first_published` first, not `updated_at`. Greenhouse boards carry
                          # evergreen pipeline reqs whose `updated_at` is refreshed constantly:
                          # Intercom's *Senior Machine Learning Scientist* read 4 Sep 2026 on
                          # `updated_at` and 2 Nov 2025 on `first_published` (5 Sep 2026 morning).
                          # Scoring off `updated_at` hands a 10-month-old pipeline advert a +2
                          # freshness bonus. The SumUp and SoundCloud notes in instructions/COMPANIES.md
                          # already say to score off `first_published`; this makes the collector
                          # emit it.
                          url=j.get("absolute_url", ""), date=j.get("first_published", "") or j.get("updated_at", ""),
                          desc=j.get("content", "")))
    elif kind in ("lever", "lever_eu"):
        for j in json.loads(raw):
            o.append(dict(title=j.get("text", ""),
                          location=(j.get("categories") or {}).get("location", ""),
                          url=j.get("hostedUrl", ""), date=str(j.get("createdAt", "")),
                          # 2 Oct 2026: `descriptionPlain` is the opening only. The requirements
                          # are in `lists` and the closing section in `additional`; on the one
                          # `lever` board they held 8,400 of 9,100 characters per job.
                          desc=join_html(j.get("description") or j.get("descriptionPlain", ""),
                                         *[(l.get("text", ""), "<ul>%s</ul>" % (l.get("content") or ""))
                                           for l in (j.get("lists") or []) if isinstance(l, dict)],
                                         j.get("additional") or j.get("additionalPlain", ""),
                                         j.get("salaryDescription") or j.get("salaryDescriptionPlain", ""))))
    elif kind == "ashby":
        # `location` is the PRIMARY location only; a job open in several offices carries the
        # rest under `secondaryLocations`. Reading `location` alone hid SpAItial's entire
        # board from 22 Aug 2026 back: every SpAItial job says `location: "London"` with
        # Munich sitting in secondaryLocations, so filter_run's loc_ok saw a pure-UK job and
        # threw all nine away. They only surfaced through the Getro copy, which writes the
        # location as "Munich, Germany, London, UK". Join every office into one string so a
        # German office anywhere in the list is visible to the location filter.
        for j in json.loads(raw).get("jobs", []):
            locs = [j.get("location") or ""]
            for s in (j.get("secondaryLocations") or []):
                # NB: never bind this to `name` — that is the company parameter, and shadowing
                # it here stamped the last secondary location onto every job on the board as
                # its employer. 436 of 2983 rows on 22 Aug 2026 evening came back with a city
                # ("Berlin", "Kyiv", "Home Office") where the company should be.
                locname = s.get("location") if isinstance(s, dict) else str(s)
                addr = ((s.get("address") or {}).get("postalAddress") or {}) if isinstance(s, dict) else {}
                part = ", ".join(x for x in [locname, addr.get("addressCountry")] if x)
                if part:
                    locs.append(part)
            # The URL above already asks for compensation. Ashby publishes it on very few
            # postings (1 of 109 at Preply, 0 of 31 at Moss, checked 21 Sep 2026), but when it
            # is there it sits outside the description and no reader would ever see it.
            comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
            o.append(dict(title=j.get("title", ""),
                          location="; ".join(x for x in locs if x)[:120],
                          url=j.get("jobUrl", ""), date=j.get("publishedAt", "") or "",
                          salary=comp,
                          desc=j.get("descriptionHtml") or j.get("descriptionPlain", "")))
    elif kind == "personio":
        for m in re.finditer(r"<position>(.*?)</position>", raw, re.S):
            b = m.group(1)
            g = lambda t: (re.search(r"<%s>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</%s>" % (t, t), b, re.S) or [None, ""])[1]
            pid = g("id")
            # 2 Oct 2026: the text is one <jobDescription> per section, each a <name> and a CDATA
            # <value>. Stripping the whole <position> block put the id, department, keywords and
            # a stray "]]>" into every description.
            secs = [(strip(_cdata(n)), _cdata(v)) for n, v in re.findall(
                r"<jobDescription>\s*<name>(.*?)</name>\s*<value>(.*?)</value>\s*</jobDescription>", b, re.S)]
            # The feed states a salary on a few postings (33 of 623 on 2 Oct 2026), outside the text.
            sal = re.search(r"<salaryInformation>(.*?)</salaryInformation>", b, re.S)
            pay = ""
            if sal:
                f = lambda t: (re.search(r"<%s>(.*?)</%s>" % (t, t), sal.group(1), re.S) or [None, ""])[1].strip()
                lo, hi = f("min").split(".")[0], f("max").split(".")[0]
                per = {"yearly": "", "monthly": " a month", "hourly": " an hour"}.get(f("type"), " " + f("type") if f("type") else "")
                pay = ("%s %s%s" % (f("currencyCode") or "EUR", "-".join(x for x in [lo, hi] if x), per)).strip() if lo or hi else ""
            o.append(dict(title=strip(g("name")), location=strip(g("office")),
                          url="https://%s.jobs.personio.de/job/%s" % (slug, pid),
                          date=strip(g("createdAt")), salary=pay, desc=join_html(*secs)))
    elif kind in ("teamtailor", "teamtailor_feed", "teamtailor_custom"):
        d = json.loads(raw)
        for j in d.get("items", []) or d.get("jobs", []):
            o.append(dict(title=j.get("title", ""), location=j.get("location", "") or "",
                          url=j.get("url", "") or j.get("id", ""),
                          date=j.get("date_published", "") or j.get("created-at", ""),
                          desc=j.get("content_html", "") or j.get("body", "")))
    elif kind == "workable":
        for j in json.loads(raw).get("jobs", []):
            o.append(dict(title=j.get("title", ""),
                          location=", ".join(x for x in [j.get("city"), j.get("country")] if x),
                          url=j.get("url", ""), date=j.get("published_on", "") or "",
                          desc=join_html(j.get("description"), j.get("requirements"), j.get("benefits"))))
    elif kind in ("recruitee", "recruitee_custom"):
        for j in json.loads(raw).get("offers", []):
            o.append(dict(title=j.get("title", ""),
                          location=", ".join(x for x in [j.get("city"), j.get("country_code")] if x),
                          url=j.get("careers_url") or j.get("careers_apply_url", ""),
                          date=j.get("published_at") or j.get("created_at", ""),
                          desc=join_html(j.get("description"), j.get("requirements"))))
    elif kind == "pinpoint":
        d = json.loads(raw)
        for j in (d.get("data") if isinstance(d, dict) else d) or []:
            loc = j.get("location") or {}
            o.append(dict(title=j.get("title", ""),
                          location=", ".join(x for x in [loc.get("city"), loc.get("province")] if x),
                          url=j.get("url", ""),
                          date=j.get("published_at") or j.get("created_at") or "",
                          # 2 Oct 2026: there is no `requirements` field. The tasks and the
                          # requirements are in the two fields below, 3,200 of 5,100 characters.
                          desc=join_html(j.get("description"),
                                         ("Key responsibilities", j.get("key_responsibilities")),
                                         ("Skills, knowledge and expertise", j.get("skills_knowledge_expertise")),
                                         ("Benefits", j.get("benefits")))))
    elif kind == "hirehive":
        import datetime
        for j in json.loads(raw).get("jobs", []):
            ts = j.get("publishedDate") or j.get("createdDate")
            date = (datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                    if isinstance(ts, (int, float)) else "")
            ctry = (j.get("country") or {}).get("name") or ""
            o.append(dict(title=j.get("title", ""),
                          location=", ".join(x for x in [j.get("location"), ctry] if x),
                          url=j.get("hostedUrl", ""), date=date,
                          desc=(j.get("description") or {}).get("html", "") or (j.get("description") or {}).get("text", "")))
    elif kind == "smartrecruiters":
        for j in json.loads(raw).get("content", []):
            loc = j.get("location") or {}
            o.append(dict(title=j.get("name", ""),
                          location=", ".join(x for x in [loc.get("city"), loc.get("country")] if x),
                          url="https://jobs.smartrecruiters.com/%s/%s" % (slug, j.get("id")),
                          date=j.get("releasedDate", "") or "", desc=""))
    elif kind == "personio_html":
        # The anchor text is title + location + employment type run together, e.g.
        # "Software Engineer - AI Workflows (m/f/d) NL, DE Full-time Permanent employee".
        # Left whole it defeats the repeat check: on 9 Aug 2026 evening EnOcean's AI Workflows
        # role — sent 4 Aug — came back as new, because the trailing noise sank the fuzzy
        # title overlap in is_repeat. Split the tail off and keep it as the location instead.
        #
        # Two extensions, both found on botario 17 Aug 2026 evening, where the whole tail
        # survived and the title came off the board as "Machine Learning Engineer (all
        # genders) Bremen, Mainz, Berlin, München, Mannheim Full or part-time Permanent
        # employee". That title has five tokens of pure noise on the end, which sinks the
        # Jaccard in `same_title` to 0.44 and let a role sent on 15 August through as new
        # for the third run running.
        #
        # 1. The employment type is not always one of the four fixed words. botario writes
        #    "Full or part-time", Personio also emits "Voll- oder Teilzeit" and a bare
        #    "Permanent employee" when no working-time is set, and none of those anchored.
        # 2. Locations are not always two-letter codes. Boards with several offices spell
        #    them out in full, so peel real place names off the end of what is left and put
        #    them in the location where they belong, rather than leaving them in the title.
        TAIL = re.compile(
            r"\s+((?:[A-Z]{2}(?:,\s*[A-Z]{2})*\s+)?"
            r"(?:Full(?:\s+or\s+part)?[-\s]?time|Part(?:\s+or\s+full)?[-\s]?time|"
            r"Voll(?:-?\s*(?:oder|und)\s*Teil)?zeit|Teil(?:-?\s*(?:oder|und)\s*Voll)?zeit|"
            r"Intern|Internship|Working Student|Werkstudent|Temporary|Fixed term|"
            r"Permanent employee|Limited contract)\b.*)$")

        def peel_places(head):
            """Move trailing place names out of the title and into the location."""
            toks, places = head.split(), []
            while toks and fold(toks[-1].strip(",")) in PLACE:
                places.insert(0, toks.pop().strip(","))
            # Never strip the title down to nothing: "Berlin" alone is not a job, but a
            # role genuinely titled e.g. "Remote Engineer" must keep its first word.
            if len(toks) < 2:
                return head, ""
            return " ".join(toks).rstrip(" ,-|"), ", ".join(places)

        for m in re.finditer(r'href="(/job/(\d+)[^"]*)"[^>]*>(.*?)</a>', raw, re.S):
            text = strip(m.group(3))[:200]
            tail = TAIL.search(text)
            title, loc = (text[:tail.start()].strip(), tail.group(1).strip()) if tail else (text, "")
            title, extra = peel_places(title)
            loc = ", ".join(x for x in [extra, loc] if x)
            o.append(dict(title=title[:120],
                          location=loc[:60], url="https://%s.jobs.personio.com%s" % (slug, m.group(1)),
                          date="", desc=""))
    elif kind == "join":
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw, re.S)
        if m:
            items = (json.loads(m.group(1)).get("props", {}).get("pageProps", {})
                     .get("initialState", {}).get("jobs", {}).get("items") or [])
            for j in items:
                # `locations` is null on every row seen. The place is under `city`, which is a
                # NESTED dict {"cityName", "countryName"}, not a string — reading it as a string
                # yields a bare "hybrid" location, which `loc_ok` in filter_run.py then drops as
                # neither German nor remote. That would have silently binned both new boards.
                city = j.get("city") if isinstance(j.get("city"), dict) else {}
                loc = ", ".join(x for x in [city.get("cityName"), city.get("countryName")]
                                if isinstance(x, str) and x)
                wt = j.get("workplaceType")
                if isinstance(wt, str) and wt and wt.lower() != "onsite":
                    loc = "%s (%s)" % (loc, wt.lower()) if loc else wt.lower()
                jid = j.get("idParam") or j.get("id")
                o.append(dict(title=j.get("title", ""), location=loc[:80],
                              url="https://join.com/companies/%s/%s" % (slug, jid),
                              date=j.get("createdAt", "") or "", desc=""))
    elif kind == "avature":
        # One <li class="list__item ..."> per role. Title and url live in
        # list__item__text__title; the subtitle runs "Location · Seniority · Type · blurb"
        # with <span> · </span> separators, so the location is everything before the first
        # dot. Split on the <li> first rather than running one regex over the whole page,
        # because the non-greedy spans would otherwise stitch one job's title to the next
        # job's subtitle.
        #
        # No posting date is published anywhere on the board, so `date` stays empty and
        # these score without a freshness bonus. Do not invent one. Closed roles return
        # HTTP 410 rather than disappearing quietly, so a 410 on a link the radar sent
        # earlier means the role was filled, not that this parser broke.
        for chunk in raw.split('class="list__item ')[1:]:
            t = re.search(r'list__item__text__title.*?<a\s+href="([^"]+)"[^>]*>(.*?)</a>',
                          chunk, re.S)
            if not t:
                continue
            s = re.search(r'list__item__text__subtitle[^>]*>(.*?)</div>', chunk, re.S)
            loc = strip(s.group(1)).split("·")[0].strip() if s else ""
            o.append(dict(title=strip(t.group(2))[:120], location=loc[:60],
                          url=t.group(1), date="", desc=""))
    elif kind == "breezy":
        for j in json.loads(raw):
            loc = j.get("location") or {}
            city = (loc.get("city") or "") if isinstance(loc, dict) else str(loc)
            o.append(dict(title=j.get("name", ""), location=city,
                          url=j.get("url", "") or ("https://%s.breezy.hr/p/%s" % (slug, j.get("id"))),
                          date=j.get("published_date", "") or "", desc=""))
    for j in o:
        j["company"], j["source"] = name, "ats:" + kind
        # Every branch above leaves the source HTML in `desc`. It is cleaned here, once, whole.
        raw = j.get("desc") or ""
        j["desc"] = html_to_text(raw)
        if KEEP_RAW:
            j["desc_raw"] = raw
    return o


def one(b):
    kind, slug, name = b
    url = URLS[kind].format(s=slug)
    try:
        raw = fetch(url)
        jobs = parse(kind, slug, name, raw)
        # SmartRecruiters caps a response at 100 postings and reports the real size in
        # `totalFound`. Without paging, AUTO1 returned 100 of 532 on 30 Aug 2026 and the
        # missing 432 are not ordered in any useful way, so a computer-vision role could sit
        # in the unread tail every run and never be seen. Scalable Capital fits in one page,
        # which is why this went unnoticed until a bigger board was added.
        if kind == "smartrecruiters":
            total = json.loads(raw).get("totalFound") or 0
            for off in range(100, min(total, 2000), 100):
                jobs += parse(kind, slug, name, fetch(url + "&offset=%d" % off))
        # join.com paginates the hydration payload at a FIXED five jobs per page and ignores
        # `pageSize` entirely (same validator that rejects it on the public REST endpoint), so
        # reading only the board url gives 5 of however many exist. Found 27 Sep 2026 morning
        # on omnisent, whose ML Engineer role — the only ML seat on a 15-job board — sits on
        # page 3 and had never been collected. Checked across all twelve join slugs that day:
        # 32 of 67 jobs were invisible, worst of them motor-ai at 5 of 16. `?page=N` works and
        # the real size is in `initialState.jobs.pagination`, so walk it like SmartRecruiters.
        if kind == "join":
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw, re.S)
            pages = 1
            if m:
                pages = ((json.loads(m.group(1)).get("props", {}).get("pageProps", {})
                          .get("initialState", {}).get("jobs", {})
                          .get("pagination", {}) or {}).get("pageCount") or 1)
            for pg in range(2, min(int(pages), 40) + 1):
                jobs += parse(kind, slug, name, fetch(url + "?page=%d" % pg))
        return name, slug, kind, jobs, None
    except urllib.error.HTTPError as e:
        return name, slug, kind, [], "HTTP %s" % e.code
    except Exception as e:
        return name, slug, kind, [], str(e)[:80]


def main():
    all_jobs, report = [], []
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        for name, slug, kind, jobs, err in ex.map(one, BOARDS):
            report.append(dict(company=name, slug=slug, kind=kind, n=len(jobs), err=err))
            all_jobs.extend(jobs)
            print("%-22s %-16s %-18s %4s %s" % (name[:22], slug[:16], kind, len(jobs), err or ""),
                  file=sys.stderr)

    json.dump(all_jobs, open(sys.argv[1], "w"), ensure_ascii=False)
    json.dump(report, open(sys.argv[2] if len(sys.argv) > 2 else sys.argv[1] + ".report",
                                "w"), ensure_ascii=False, indent=1)
    print("TOTAL %d jobs from %d boards" % (len(all_jobs), len(BOARDS)), file=sys.stderr)


if __name__ == "__main__":
    main()
