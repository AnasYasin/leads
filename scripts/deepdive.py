#!/usr/bin/env python3
"""What the employer's own ATS knows that the advert does not.

    deepdive.py <apply-url>          detect the board, pull every open role
    deepdive.py <pack-id>            same, resolved from job_radar/jobs/

Answers four things a single job advert cannot:
  1. the true first-published date, which catches LinkedIn and XING reposts
  2. how long the role has really been open
  3. every other role the employer has open, so the team shape and the hiring
     wave are visible instead of guessed
  4. structured fields the advert never prints - Personio carries seniority and
     yearsOfExperience, Greenhouse carries first_published, Ashby carries
     compensation.
"""
import datetime, json, re, sys, urllib.request, urllib.error

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9,de;q=0.8"}
TODAY = datetime.date.today()
ML = re.compile(r"machine learning|\bml\b|\bai\b|artificial intel|data scien|data engineer|"
                r"deep learning|nlp|computer vision|research|künstliche|\bki\b|llm|mlops", re.I)


def get(url, hdr=None, timeout=30):
    req = urllib.request.Request(url, headers=hdr or UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(3000000).decode("utf-8", "replace")


def days(iso):
    if not iso:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso)
    if not m:
        return None
    return (TODAY - datetime.date(*map(int, m.groups()))).days


def detect(url):
    """(kind, slug) from an apply url."""
    u = url.strip()
    pats = [
        (r"([a-z0-9\-\.]+)\.jobs\.personio\.(?:de|com)", "personio"),
        (r"(?:boards|job-boards)(?:-api)?\.(?:eu\.)?greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9\-]+)", "greenhouse"),
        (r"jobs\.ashbyhq\.com/([^/?#]+)", "ashby"),
        (r"jobs\.lever\.co/([^/?#]+)", "lever"),
        (r"([a-z0-9\-]+)\.recruitee\.com", "recruitee"),
        (r"apply\.workable\.com/([^/?#]+)", "workable"),
        (r"careers\.smartrecruiters\.com/([^/?#]+)", "smartrecruiters"),
        (r"([a-z0-9\-]+)\.teamtailor\.com", "teamtailor"),
        (r"([a-z0-9\-]+)\.wd\d+\.myworkdayjobs\.com", "workday"),
    ]
    for pat, kind in pats:
        m = re.search(pat, u, re.I)
        if m:
            return kind, m.group(1)
    # SAP SuccessFactors career sites (jobs.sonova.com and many others): job urls look like
    # https://<host>/job/<City>-<Title>/<id>/ and the whole board is server-rendered at
    # https://<host>/search/?q=&sortColumn=referencedate&sortDirection=desc, 25 rows a page.
    # Verified 8 Sep 2026 on jobs.sonova.com. The slug is the host.
    # Some sites mount the board under a prefix (career.witglobal.net/wuerth-it/job/...), so the
    # slug is host plus prefix; the search page sits at the same prefix.
    m = re.match(r"https?://([a-z0-9.\-]+(?:/[a-z0-9\-]+)?)/job/[^/]+/\d{6,}/?", u, re.I)
    if m:
        return "successfactors", m.group(1)
    return None, None


# ---------- per-board readers: return [{title, date, dept, loc, extra, url}] ----------
def personio(slug):
    x = get("https://%s.jobs.personio.de/xml" % slug)
    out = []
    for blk in re.findall(r"<position>(.*?)</position>", x, re.S):
        f = lambda t: (re.search(r"<%s>(.*?)</%s>" % (t, t), blk, re.S).group(1).strip()
                       if re.search(r"<%s>(.*?)</%s>" % (t, t), blk, re.S) else "")
        extra = " · ".join(v for v in ["seniority=" + f("seniority") if f("seniority") else "",
                                       "yrs=" + f("yearsOfExperience") if f("yearsOfExperience") else "",
                                       f("employmentType"), f("schedule")] if v and not v.endswith("="))
        out.append({"title": f("name"), "date": f("createdAt")[:10], "dept": f("department"),
                    "loc": f("office"), "extra": extra,
                    "url": "https://%s.jobs.personio.de/job/%s" % (slug, f("id"))})
    return out


def greenhouse(slug):
    for host in ("boards-api.greenhouse.io", "job-boards.eu.greenhouse.io"):
        try:
            d = json.loads(get("https://boards-api.greenhouse.io/v1/boards/%s/jobs" % slug))
            break
        except Exception:
            continue
    else:
        return []
    out = []
    for j in d.get("jobs", []):
        dep = ", ".join(x.get("name", "") for x in (j.get("departments") or [])[:2])
        out.append({"title": j.get("title", ""), "date": (j.get("first_published") or j.get("updated_at") or "")[:10],
                    "dept": dep, "loc": (j.get("location") or {}).get("name", ""),
                    "extra": "", "url": j.get("absolute_url", "")})
    return out


def ashby(slug):
    d = json.loads(get("https://api.ashbyhq.com/posting-api/job-board/%s?includeCompensation=true" % slug))
    out = []
    for j in d.get("jobs", []):
        comp = j.get("compensation") or {}
        summ = comp.get("compensationTierSummary") or ""
        out.append({"title": j.get("title", ""), "date": (j.get("publishedAt") or "")[:10],
                    "dept": j.get("department") or j.get("team") or "", "loc": j.get("location", ""),
                    "extra": summ, "url": j.get("jobUrl", "")})
    return out


def lever(slug):
    for host in ("api.eu.lever.co", "api.lever.co"):
        try:
            d = json.loads(get("https://%s/v0/postings/%s?mode=json" % (host, slug)))
            break
        except Exception:
            continue
    else:
        return []
    out = []
    for j in d:
        ts = j.get("createdAt")
        iso = datetime.datetime.utcfromtimestamp(ts / 1000).date().isoformat() if ts else ""
        c = j.get("categories") or {}
        out.append({"title": j.get("text", ""), "date": iso, "dept": c.get("team", ""),
                    "loc": c.get("location", ""), "extra": c.get("commitment", ""),
                    "url": j.get("hostedUrl", "")})
    return out


def recruitee(slug):
    d = json.loads(get("https://%s.recruitee.com/api/offers/" % slug))
    return [{"title": o.get("title", ""), "date": (o.get("published_at") or "")[:10],
             "dept": o.get("department", ""), "loc": o.get("location", ""),
             "extra": o.get("employment_type", ""), "url": o.get("careers_url", "")}
            for o in d.get("offers", [])]


def workable(slug):
    d = json.loads(get("https://apply.workable.com/api/v1/widget/accounts/%s?details=true" % slug))
    return [{"title": j.get("title", ""), "date": (j.get("published_on") or "")[:10],
             "dept": j.get("department", ""), "loc": (j.get("location") or {}).get("city", ""),
             "extra": "", "url": j.get("url", "")} for j in d.get("jobs", [])]


def smartrecruiters(slug):
    d = json.loads(get("https://api.smartrecruiters.com/v1/companies/%s/postings?limit=100" % slug))
    return [{"title": j.get("name", ""), "date": (j.get("releasedDate") or "")[:10],
             "dept": (j.get("department") or {}).get("label", ""),
             "loc": (j.get("location") or {}).get("city", ""), "extra": "",
             "url": j.get("ref", "")} for j in d.get("content", [])]


def teamtailor(slug):
    d = json.loads(get("https://%s.teamtailor.com/jobs.json" % slug))
    items = d.get("items", d if isinstance(d, list) else [])
    return [{"title": j.get("title", ""), "date": (j.get("date_published") or "")[:10],
             "dept": "", "loc": "", "extra": "", "url": j.get("url", "")} for j in items]


def workday(slug, url):
    m = re.search(r"myworkdayjobs\.com/(?:[a-z\-]+/)?([^/]+)/job/(.+)$", url)
    if not m:
        return []
    site, path = m.group(1), m.group(2)
    api = "https://%s.wd3.myworkdayjobs.com/wday/cxs/%s/%s/job/%s" % (slug, slug, site, path)
    try:
        d = json.loads(get(api, dict(UA, Accept="application/json")))
    except Exception:
        return []
    ji = d.get("jobPostingInfo", {})
    return [{"title": ji.get("title", ""), "date": (ji.get("startDate") or "")[:10], "dept": "",
             "loc": ji.get("location", ""), "extra": ji.get("postedOn", ""), "url": url}]


SF_DATE = re.compile(r"([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})|(\d{1,2})\.(\d{1,2})\.(\d{4})")
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
          "sep": 9, "oct": 10, "nov": 11, "dec": 12, "mär": 3, "mai": 5, "okt": 10, "dez": 12}


def _sf_date(txt):
    m = SF_DATE.search(txt or "")
    if not m:
        return ""
    try:
        if m.group(1):
            return datetime.date(int(m.group(3)), MONTHS[m.group(1).lower()[:3]], int(m.group(2))).isoformat()
        return datetime.date(int(m.group(6)), int(m.group(5)), int(m.group(4))).isoformat()
    except Exception:
        return ""


def successfactors(host, target_title="", pages=8):
    """Newest `pages` x 25 roles on the board, plus a keyword search for the target title so an
    older target still shows up. Big boards (Sonova has hundreds of roles worldwide) would
    otherwise take a minute to page through."""
    import html as _html
    out, seen = [], set()
    urls = ["https://%s/search/?q=&sortColumn=referencedate&sortDirection=desc&startrow=%d" % (host, 25 * i)
            for i in range(pages)]
    if target_title:
        q = re.sub(r"\(.*?\)", " ", target_title).split(" - ")[0].strip()
        urls.insert(0, "https://%s/search/?q=%s&sortColumn=referencedate&sortDirection=desc" % (host, urllib.request.quote(q)))
    for url in urls:
        try:
            t = get(url)
        except Exception:
            break
        rows = re.findall(r'<tr class="data-row[^"]*">(.*?)</tr>', t, re.S)
        if not rows:
            if url is urls[0] and target_title:
                continue
            break
        for r in rows:
            m = re.search(r'class="jobTitle-link"[^>]*href="([^"]+)"[^>]*>\s*(.*?)\s*</a>', r, re.S)
            if not m:
                continue
            href = m.group(1)
            if href in seen:
                continue
            seen.add(href)
            loc = re.search(r'class="jobLocation">\s*(.*?)\s*</span>', r, re.S)
            date = re.search(r'class="jobDate[^"]*">\s*(.*?)\s*</span>', r, re.S)
            bare = host.split("/")[0]
            out.append({"title": _html.unescape(m.group(2)).strip(), "date": _sf_date(date.group(1) if date else ""),
                        "dept": "", "loc": _html.unescape(loc.group(1)).strip() if loc else "", "extra": "",
                        "url": ("https://" + bare + href) if href.startswith("/") else href})
    return out


READERS = {"personio": personio, "greenhouse": greenhouse, "ashby": ashby, "lever": lever,
           "recruitee": recruitee, "workable": workable, "smartrecruiters": smartrecruiters,
           "teamtailor": teamtailor}


def run(url, target_title=""):
    kind, slug = detect(url)
    if not kind:
        print("no ATS pattern matched: %s" % url)
        return
    print("== %s board `%s` ==" % (kind, slug))
    try:
        jobs = (workday(slug, url) if kind == "workday" else
                successfactors(slug, target_title) if kind == "successfactors" else READERS[kind](slug))
    except urllib.error.HTTPError as e:
        print("   board error HTTP %s" % e.code)
        return
    except Exception as e:
        print("   board error %s" % str(e)[:90])
        return
    if not jobs:
        print("   board returned no roles" + (" (site reachable but not the standard SuccessFactors template)"
                                             if kind == "successfactors" else ""))
        return
    dated = [j for j in jobs if j["date"]]
    print("   %d open roles, %d carry a date%s" % (len(jobs), len(dated),
          "  (newest 200 plus a title search; the full board is bigger)" if kind == "successfactors" else ""))
    if dated:
        fresh30 = sum(1 for j in dated if (days(j["date"]) or 999) <= 30)
        print("   %d posted in the last 30 days  (hiring velocity)" % fresh30)
    print()
    if target_title and not any(target_title.lower()[:28] in j["title"].lower() for j in jobs):
        print("   target not in this listing%s; the job page itself may still be live, check_live.py decides that"
              % (" (newest 200 plus a title search)" if kind == "successfactors" else ""))
    for j in sorted(jobs, key=lambda j: j["date"] or "0000"):
        d = days(j["date"])
        age = "%4d d" % d if d is not None else "  ?  "
        mark = " <-- TARGET" if target_title and target_title.lower()[:28] in j["title"].lower() else \
               ("  *ML*" if ML.search(j["title"]) else "")
        print("   %-11s %s  %-58s %-22s %s%s" % (j["date"] or "no date", age, j["title"][:58],
                                                 (j["dept"] or j["loc"])[:22], j["extra"][:30], mark))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(1)
    run(a[0], a[1] if len(a) > 1 else "")
