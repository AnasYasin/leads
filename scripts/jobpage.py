#!/usr/bin/env python3
"""The full text of one job posting, from its link.

Added 2 Oct 2026 (docs/PROBLEMS.md 1.4 and 1.5). Getro, SmartRecruiters, JOIN, Avature, Breezy and the
Personio HTML boards hand over a title card and no text, and nothing fetched the text afterwards.
On 30 Sep, 49 of 248 pool rows were sent to the reading step with no description at all.

`read(url)` tries the cheapest reliable source first and stops at the first one that returns text:

  1. the ATS's own API, when the link is on a known ATS (SmartRecruiters, Greenhouse, Lever, Ashby,
     Personio, Workable, Recruitee, Workday, BambooHR, Teamtailor, LinkedIn). Whole text, no page chrome.
  2. the page's JSON-LD `JobPosting` block. Employers publish it for Google Jobs, so it carries the
     whole description and nothing else.
  3. a description found in the page's embedded JSON (Next.js and similar).
  4. the main content of the page, with navigation, header, footer and forms removed.

It returns {"desc", "desc_src"} or {"error"}. The text is cleaned by textclean.html_to_text and is
never cut. A page that needs a browser to render (Notion, some Workday tenants) returns an error
that says so, and the row stays in the list without text.

    python3 scripts/jobpage.py <url> [<url> ...]
"""
import gzip
import html
import json
import re
import zlib
import sys
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textclean import html_to_text, join_html  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9,de;q=0.8"}
# Shorter than this is a cookie banner, a login wall or an empty shell, not a posting.
MIN_CHARS = 300
TIMEOUT = 30

_cache, _cache_lock = {}, threading.Lock()
_host_locks, _host_guard = {}, threading.Lock()
# How many requests may run against one host at a time. LinkedIn answers 429 above three.
PER_HOST = 3


class Unreadable(Exception):
    pass


class Gone(Unreadable):
    """The link answers 404 or 410, or the ATS says the posting is closed. On its own a 404 proves
    little: careers.cognizant.com answers a script with 404 and a browser with a bot check. `read`
    reports a posting as gone only on a 410, on an ATS's explicit "closed", or when the ATS API and
    the page both say 404."""

    def __init__(self, msg, sure=False):
        super().__init__(msg)
        self.sure = sure


# What a bot wall or an error page calls itself. Checked on short pages only.
WALL = re.compile(r"<title>[^<]*(just a moment|security check|access denied|attention required|are you a robot|"
                  r"captcha|pardon our interruption|request blocked|403 forbidden)", re.I)
# Hosts that never show the posting to a script. The BA page sits behind a captcha.
NO_FETCH = re.compile(r"(^|\.)arbeitsagentur\.de$")


def _decode(raw, headers):
    enc = (headers.get("Content-Encoding") or "").lower()
    try:
        if "gzip" in enc or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        elif "deflate" in enc:
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
        elif "br" in enc:
            import brotli                      # only when the server sends it unasked
            raw = brotli.decompress(raw)
    except Exception as e:
        raise Unreadable("could not decompress the response (%s)" % (enc or type(e).__name__))
    cs = headers.get_content_charset() or "utf-8"
    try:
        t = raw.decode(cs, "replace")
    except LookupError:
        t = raw.decode("utf-8", "replace")
    if t.count("\ufffd") > max(20, len(t) // 100):
        raise Unreadable("the response is not text")
    return t


def _host_slot(host):
    with _host_guard:
        if host not in _host_locks:
            _host_locks[host] = threading.Semaphore(PER_HOST)
        return _host_locks[host]


def fetch(url, accept=None, data=None, tries=3, info=None):
    """The response body as text. Retries a 429 or a 5xx with a pause; raises on anything else.
    `info`, when given, receives the address the request ended on as info["final"]."""
    host = urllib.parse.urlparse(url).netloc.lower()
    if NO_FETCH.search(host):
        raise Unreadable("%s shows the posting behind a captcha" % host)
    hdr = dict(UA)
    hdr["Accept-Encoding"] = "gzip, deflate"
    if accept:
        hdr["Accept"] = accept
    if data is not None:
        hdr["Content-Type"] = "application/json"
    last = None
    for i in range(tries):
        try:
            with _host_slot(host):
                req = urllib.request.Request(url, headers=hdr, data=data)
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    raw, headers, final = r.read(), r.headers, r.geturl()
            if info is not None:
                info["final"] = final
            # A Personio page that is not public redirects to personio.com, which then answers a
            # script with 429. That is how "meshcapade answers 429 on every run" came about. It
            # does not mean the job is closed: Hornetsecurity keeps its feed public and its pages
            # private, and all 98 of its jobs redirect, the open ones too (checked 2 Oct 2026).
            if urllib.parse.urlparse(final).netloc.lower() in ("personio.com", "www.personio.com", "www.personio.de") \
                    and "jobs.personio" in host:
                raise Unreadable("the Personio page is not public (it redirects to personio.com)")
            return _decode(raw, headers)
        except Unreadable:
            raise
        except urllib.error.HTTPError as e:
            last = "HTTP %d" % e.code
            if e.code in (404, 410):
                raise Gone(last, sure=e.code == 410)
            if e.code == 429 and "jobs.personio" in host and "jobs.personio" not in (e.geturl() or host):
                raise Unreadable("the Personio page is not public (it redirects to personio.com)")
            if e.code in (429, 500, 502, 503, 504) and i + 1 < tries:
                time.sleep(4 * (i + 1) if e.code != 429 else 12 * (i + 1))
                continue
            if e.code in (401, 403):
                raise Unreadable(last + ", the site blocks scripts")
            raise Unreadable(last)
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, str(e)[:80])
            if i + 1 < tries:
                time.sleep(2 * (i + 1))
                continue
            raise Unreadable(last)
    raise Unreadable(last or "no response")


def cached(url, accept=None):
    """One fetch per url in a run. Board feeds (Ashby, Personio) serve many rows each."""
    with _cache_lock:
        lock = _cache.setdefault(url, threading.Lock())
    if isinstance(lock, str):
        return lock
    if isinstance(lock, Exception):
        raise lock
    with lock:
        with _cache_lock:
            v = _cache.get(url)
        if isinstance(v, str):
            return v
        if isinstance(v, Exception):
            raise v
        try:
            t = fetch(url, accept)
        except Unreadable as e:
            with _cache_lock:
                _cache[url] = e
            raise e
        with _cache_lock:
            _cache[url] = t
        return t


# --- ATS APIs ---------------------------------------------------------------------------------

def _smartrecruiters(m):
    d = json.loads(fetch("https://api.smartrecruiters.com/v1/companies/%s/postings/%s" % (m.group(1), m.group(2)),
                         "application/json"))
    sec = (d.get("jobAd") or {}).get("sections") or {}
    order = ["companyDescription", "jobDescription", "qualifications", "additionalInformation"]
    keys = [k for k in order if k in sec] + [k for k in sec if k not in order]
    return join_html(*[((sec[k] or {}).get("title", ""), (sec[k] or {}).get("text", "")) for k in keys
                       if isinstance(sec[k], dict)])


def _greenhouse(m):
    d = json.loads(fetch("https://boards-api.greenhouse.io/v1/boards/%s/jobs/%s" % (m.group(1), m.group(2)),
                         "application/json"))
    return d.get("content") or ""


def lever_html(j):
    """A Lever posting's whole text: the opening, every list (tasks, requirements), the closing."""
    return join_html(j.get("description") or j.get("descriptionPlain", ""),
                     *[(l.get("text", ""), "<ul>%s</ul>" % (l.get("content") or ""))
                       for l in (j.get("lists") or []) if isinstance(l, dict)],
                     j.get("additional") or j.get("additionalPlain", ""),
                     j.get("salaryDescription") or j.get("salaryDescriptionPlain", ""))


def _lever(m):
    api = "https://api.eu.lever.co" if m.group(1) else "https://api.lever.co"
    return lever_html(json.loads(fetch("%s/v0/postings/%s/%s" % (api, m.group(2), m.group(3)), "application/json")))


def _ashby(m):
    org, jid = m.group(1), m.group(2)
    d = json.loads(cached("https://api.ashbyhq.com/posting-api/job-board/%s?includeCompensation=true" % org,
                          "application/json"))
    for j in d.get("jobs") or []:
        if j.get("id") == jid or jid in (j.get("jobUrl") or ""):
            return j.get("descriptionHtml") or j.get("descriptionPlain") or ""
    # The feed lists every open posting. The page of a closed one carries `"posting":null`.
    try:
        if re.search(r'"posting"\s*:\s*null', fetch("https://jobs.ashbyhq.com/%s/%s" % (org, jid))):
            raise Gone("the Ashby posting is closed", sure=True)
    except Gone:
        raise
    except Unreadable:
        pass
    raise Unreadable("not on the Ashby board feed")


def personio_sections(block):
    """(section name, HTML) pairs of one <position> block in Personio's XML feed."""
    cd = lambda x: re.sub(r"^\s*<!\[CDATA\[|\]\]>\s*$", "", x or "", flags=re.S)
    return [(html_to_text(cd(n)), cd(v)) for n, v in re.findall(
        r"<jobDescription>\s*<name>(.*?)</name>\s*<value>(.*?)</value>\s*</jobDescription>", block, re.S)]


def _personio(m):
    slug, tld, pid = m.group(1), m.group(2), m.group(3)
    for t in dict.fromkeys([tld, "de", "com"]):
        try:
            xml = cached("https://%s.jobs.personio.%s/xml" % (slug, t))
        except Unreadable:
            continue
        for b in re.findall(r"<position>(.*?)</position>", xml, re.S):
            if re.search(r"<id>\s*%s\s*</id>" % pid, b):
                secs = personio_sections(b)
                if secs:
                    return join_html(*secs)
                # Some boards publish the position in the feed and leave its text out (11 boards
                # and 278 of 623 rows on 2 Oct 2026). The page has it.
                raise Unreadable("the Personio feed has no text for this job")
    raise Unreadable("not in the Personio XML feed")


def _workable(m):
    d = json.loads(fetch("https://apply.workable.com/api/v2/accounts/%s/jobs/%s" % (m.group(1), m.group(2)),
                         "application/json"))
    return join_html(d.get("description"), ("Requirements", d.get("requirements")), ("Benefits", d.get("benefits")))


def _recruitee(m):
    d = json.loads(fetch("https://%s/api/offers/%s" % (m.group(1), m.group(2)), "application/json"))
    o = d.get("offer") or d
    return join_html(o.get("description"), ("Requirements", o.get("requirements")))


def _workday(m):
    host, tenant, rest = m.group(1), m.group(2), m.group(3)
    rest = re.sub(r"^[a-z]{2}-[A-Z]{2}/", "", rest)          # a locale prefix is not part of the site
    site, _, path = rest.partition("/")
    d = json.loads(fetch("https://%s/wday/cxs/%s/%s/%s" % (host, tenant, site, path.split("?")[0]),
                         "application/json"))
    return (d.get("jobPostingInfo") or {}).get("jobDescription") or ""


def _bamboohr(m):
    d = json.loads(fetch("https://%s/careers/%s/detail" % (m.group(1), m.group(2)), "application/json"))
    return ((d.get("result") or {}).get("jobOpening") or {}).get("description") or ""


NOTION_LIST = {"bulleted_list", "numbered_list", "to_do"}
NOTION_HEAD = {"header", "sub_header", "sub_sub_header"}


def _notion(m):
    """A public Notion page through Notion's own page API. The page itself is empty without a browser."""
    host, pid = m.group(1), m.group(2)
    pid = "-".join([pid[:8], pid[8:12], pid[12:16], pid[16:20], pid[20:]])
    blocks, cursor = {}, {"stack": []}
    for chunk in range(6):
        body = json.dumps({"pageId": pid, "limit": 100, "cursor": cursor, "chunkNumber": chunk,
                           "verticalColumns": False}).encode()
        d = json.loads(fetch("https://%s/api/v3/loadPageChunk" % host, "application/json", data=body))
        for k, b in ((d.get("recordMap") or {}).get("block") or {}).items():
            v = b.get("value") or {}
            blocks[k] = v.get("value", v) if isinstance(v.get("value"), dict) else v
        cursor = d.get("cursor") or {}
        if not cursor.get("stack"):
            break
    out = []

    def walk(bid, depth=0):
        b = blocks.get(bid) or {}
        t = "".join(x[0] for x in ((b.get("properties") or {}).get("title") or []) if x and isinstance(x[0], str))
        t = html.escape(t, quote=False)
        kind = b.get("type")
        if depth and kind == "page":
            return                                  # a linked sub-page is another document
        if t.strip():
            out.append("<h3>%s</h3>" % t if kind in NOTION_HEAD or kind == "page"
                       else "<li>%s</li>" % t if kind in NOTION_LIST else "<p>%s</p>" % t)
        for c in b.get("content") or []:
            if depth < 8:
                walk(c, depth + 1)

    walk(pid)
    return "\n".join(out)


def _linkedin(m):
    t = fetch("https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/%s" % m.group(1))
    d = re.search(r'description__text[^>]*>(.*?)</div>\s*</div>', t, re.S)
    return d.group(1) if d else ""


ATS = [
    (re.compile(r"//(?:jobs|careers)\.smartrecruiters\.com/([^/?#]+)/(\d+)"), _smartrecruiters, "smartrecruiters api"),
    (re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?([^/?#&]+)(?:/jobs/|&token=)(\d+)"), _greenhouse, "greenhouse api"),
    (re.compile(r"//jobs\.(eu\.)?lever\.co/([^/?#]+)/([0-9a-f-]{36})"), _lever, "lever api"),
    (re.compile(r"//jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{36})"), _ashby, "ashby api"),
    (re.compile(r"//([a-z0-9-]+)\.jobs\.personio\.(de|com)/job/(\d+)"), _personio, "personio xml"),
    (re.compile(r"//apply\.workable\.com/([^/?#]+)/j/([A-Z0-9]+)"), _workable, "workable api"),
    (re.compile(r"//([a-z0-9-]+\.recruitee\.com)/o/([^/?#]+)"), _recruitee, "recruitee api"),
    (re.compile(r"//(([a-z0-9-]+)\.wd\d+\.myworkdayjobs\.com)/(.+)"), _workday, "workday api"),
    (re.compile(r"//([a-z0-9-]+\.bamboohr\.com)/(?:careers|jobs/view\.php\?id=)/?(\d+)"), _bamboohr, "bamboohr api"),
    (re.compile(r"linkedin\.com/jobs/view/(?:[^/?#]*-)?(\d{8,})"), _linkedin, "linkedin guest"),
    (re.compile(r"//([a-z0-9-]+\.notion\.site)/.*?([0-9a-f]{32})(?:[?#]|$)"), _notion, "notion api"),
]


# --- any other page ---------------------------------------------------------------------------

def _jsonld_jobs(page):
    for m in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            d = json.loads(m.strip(), strict=False)
        except Exception:
            try:
                d = json.loads(html.unescape(m.strip()), strict=False)
            except Exception:
                continue
        stack = [d]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, dict):
                t = x.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    yield x
                stack.extend(v for k, v in x.items() if k in ("@graph", "mainEntity", "itemListElement", "item"))


DESC_KEY = re.compile(r"desc|content|body|html|text|responsib|requirement|qualif|profile|aufgabe|profil|about", re.I)


def _embedded_json(page):
    """The longest description-like string in the page's embedded JSON state, as HTML."""
    best = ""
    for m in re.finditer(r'<script[^>]*(?:id=["\']__NEXT_DATA__["\']|type=["\']application/json["\'])[^>]*>(.*?)</script>',
                         page, re.S | re.I):
        try:
            d = json.loads(m.group(1), strict=False)
        except Exception:
            continue
        stack = [("", d)]
        while stack:
            k, x = stack.pop()
            if isinstance(x, dict):
                stack.extend(x.items())
            elif isinstance(x, list):
                stack.extend((k, v) for v in x)
            elif isinstance(x, str) and len(x) > len(best) and len(x) >= 600 and DESC_KEY.search(k) \
                    and " " in x and not x.lstrip().startswith(("{", "[", "http", "data:")):
                best = x
    return best


CHROME = re.compile(r"<(nav|header|footer|aside|form|dialog)\b[^>]*>.*?</\1>", re.S | re.I)
MAIN = [re.compile(r"<main\b[^>]*>(.*)</main>", re.S | re.I),
        re.compile(r"<article\b[^>]*>(.*)</article>", re.S | re.I)]
NOISE_LINE = re.compile(r"cookie|javascript|privacy policy|datenschutz|all rights reserved|©|accept all|alle akzeptieren", re.I)
# Buttons and links of the page around the posting, when they stand alone on a line.
BUTTON_LINE = re.compile(r"^(apply( now| for (this )?job)?|jetzt bewerben|bewerben|share( job| via \w+| on:?)?|copy link|back|"
                         r"back to (all )?(jobs|positions|careers)|zurück( zu allen stellen)?|careers|"
                         r"all jobs|alle stellen|print|drucken|liquid error.*)$", re.I)
TITLE_NOISE = re.compile(r"\b(m|w|f|d|x|gn|all genders|senior|junior|mid|sr|jr|und|and|for|the|der|die|das|in|of|mit|im)\b|[^0-9a-zà-ÿ+#]+", re.I)


def names_job(text, title):
    """True when the text is about the job with this title: at least half of the title's words are in it.
    A link that lands on a homepage, a job list or an error page fails this."""
    words = [w for w in TITLE_NOISE.sub(" ", (title or "").lower()).split() if len(w) >= 3]
    if not words:
        return True
    low = text.lower()
    return sum(1 for w in words if w in low) * 2 >= len(words)


def _main_content(page):
    body = re.sub(r"<!--.*?-->", " ", page, flags=re.S)
    for rx in MAIN:
        m = rx.search(body)
        if m and len(html_to_text(m.group(1))) >= MIN_CHARS:
            body = m.group(1)
            break
    else:
        m = re.search(r"<body\b[^>]*>(.*)</body>", body, re.S | re.I)
        body = m.group(1) if m else body
    # Repeat, so nested chrome (a nav inside a header) goes too.
    for _ in range(3):
        body, n = CHROME.subn(" ", body)
        if not n:
            break
    lines = [l for l in html_to_text(body).split("\n")
             if not (len(l) < 200 and NOISE_LINE.search(l)) and not BUTTON_LINE.match(l.strip())]
    return html_to_text("\n".join(lines))


def left_posting(asked, final):
    """True when the request was redirected away from the posting, to a more general page: the
    address it ended on is shorter and no longer carries the posting's own id or slug. A closed
    Greenhouse job redirects from /acme/jobs/4012345 to /acme?error=true, the board's job list.
    A redirect to a longer address is the posting itself under its real name (NEURA Robotics
    sends /offer-redirect/?offerApiId=... on to /offer/<title>/<id>)."""
    if not final or final.rstrip("/") == asked.rstrip("/"):
        return False
    a, f = urllib.parse.urlparse(asked), urllib.parse.urlparse(final)
    seg = lambda u: [x for x in u.path.split("/") if x]
    if len(seg(f)) >= len(seg(a)):
        return False
    keys = re.findall(r"\d{5,}|[0-9a-f]{8}-[0-9a-f-]{27}", a.path + "?" + a.query) or seg(a)[-1:]
    return not any(k in final for k in keys)


def looks_like_list(text):
    """A job list or a menu: mostly short lines. Measured 2 Oct 2026 on 14 postings read from their
    page (63 to 95% of the characters in lines of 80 or more, 18 to 44% short lines) and on a board's
    job list (18% and 78%)."""
    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) < 20:
        return False
    short = sum(1 for l in lines if len(l) < 50) / len(lines)
    long_chars = sum(len(l) for l in lines if len(l) >= 80) / max(1, len(text))
    return short > 0.6 and long_chars < 0.35


def from_page(page, title=""):
    """(text, source) from a fetched page, or raises Unreadable."""
    if len(page) < 60000 and WALL.search(page[:5000]):
        raise Unreadable("the site answers with a bot check")
    jobs = list(_jsonld_jobs(page))
    # A list page carries one JobPosting per job. Take the one with this title first.
    jobs.sort(key=lambda j: not names_job(str(j.get("title") or ""), title))
    for j in jobs:
        d = j.get("description")
        parts = [d if isinstance(d, str) else ""]
        for k, head in (("responsibilities", "Responsibilities"), ("qualifications", "Qualifications"),
                        ("skills", "Skills"), ("experienceRequirements", "Experience"),
                        ("educationRequirements", "Education"), ("jobBenefits", "Benefits")):
            v = j.get(k)
            # Only when the description does not already contain it. Many sites repeat the same text.
            if isinstance(v, str) and v.strip() and html_to_text(v)[:80] not in html_to_text(parts[0]):
                parts.append((head, v))
        t = html_to_text(join_html(*parts))
        if len(t) >= MIN_CHARS:
            return t, "json-ld"
    # The two fallbacks below take whatever text the page has, so the page must name the job.
    whole = html_to_text(page)
    t = html_to_text(_embedded_json(page))
    if len(t) >= MIN_CHARS and names_job(whole + " " + t, title):
        return t, "embedded json"
    t = _main_content(page)
    if len(t) >= MIN_CHARS:
        if not names_job(t, title):
            raise Unreadable("the page does not name this job (a homepage, a job list or an error page)")
        if looks_like_list(t):
            raise Unreadable("the page is a list of jobs, not one posting")
        return t, "page"
    raise Unreadable("no readable text on the page, %d characters (it may need a browser)" % len(t))


def read(url, title=""):
    """{"desc", "desc_src"} or {"error"} for one posting link. Never raises. `gone` is set when the
    posting is closed. `title` lets the page fallbacks check that the page is about this job."""
    url = (url or "").strip()
    if not url.startswith("http"):
        return {"error": "no link"}
    why, api_gone = [], False
    for rx, fn, name in ATS:
        m = rx.search(url)
        if not m:
            continue
        try:
            t = html_to_text(fn(m))
            if len(t) >= MIN_CHARS:
                return {"desc": t, "desc_src": name}
            why.append("%s: %d characters" % (name, len(t)))
        except Gone as e:
            if e.sure:
                return {"error": "gone: %s" % e, "gone": True}
            api_gone = True
            why.append("%s: %s" % (name, e))
        except Unreadable as e:
            why.append("%s: %s" % (name, e))
        except Exception as e:
            why.append("%s: %s %s" % (name, type(e).__name__, str(e)[:60]))
        break
    try:
        info = {}
        page = fetch(url, info=info)
        if left_posting(url, info.get("final")):
            raise Gone("the link redirects to %s" % info["final"][:80])
        t, src = from_page(page, title)
        return {"desc": t, "desc_src": src}
    except Gone as e:
        if e.sure or api_gone:
            return {"error": "gone: %s" % "; ".join(why + [str(e)]), "gone": True}
        why.append("%s, the posting may be closed" % e)
    except Unreadable as e:
        why.append(str(e))
    except Exception as e:
        why.append("%s %s" % (type(e).__name__, str(e)[:60]))
    return {"error": "; ".join(why)[:200]}


def one(j):
    """fetch_desc.py adapter: the row plus its text, or the row plus `error`."""
    out = dict(j)
    r = {"error": "no link"}
    errs = []
    for u in dict.fromkeys(x for x in (j.get("url"), j.get("apply_url"), j.get("externe_url")) if x):
        r = read(u, j.get("title") or "")
        if r.get("desc"):
            break
        errs.append(r)
    else:
        # No link gave text. "Gone" counts only when the row's own link says so.
        if errs:
            r = dict(errs[0], error="; ".join(dict.fromkeys(e["error"] for e in errs))[:200])
    out.update(r)
    return out


if __name__ == "__main__":
    for u in sys.argv[1:]:
        r = read(u)
        print("=" * 100)
        print(u)
        if r.get("error"):
            print("UNREADABLE:", r["error"])
        else:
            print("source: %s, %d characters, %d words\n" % (r["desc_src"], len(r["desc"]), len(r["desc"].split())))
            print(r["desc"])
