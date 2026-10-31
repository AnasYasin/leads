#!/usr/bin/env python3
"""Pull full descriptions for a chosen subset of candidates.

Usage: read_jobs.py <scratchdir> <substring> [<substring> ...]
Matches candidates whose "company | title" contains any substring (case-insensitive).
Bundesagentur rows get a v4 detail call; ATS rows print the description already
collected; anything else gets a plain fetch of its url.
"""
import base64, json, re, sys, os, urllib.request, urllib.error
import concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lang_band import band as lang_band
from trim_desc import trim
from textclean import html_to_text
import jobpage

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
BA_HDR = dict(UA); BA_HDR["X-API-Key"] = "jobboerse-jobsuche"

# 29 Sep 2026: importable, so scripts/fetch_desc.py can reuse one() without the command line.
needles = []


def one(j):
    key = ("%s | %s" % (j["company"], j["title"])).lower()
    if needles and not any(n in key for n in needles):
        return None
    src, out = j["source"], dict(j)
    try:
        if src == "Bundesagentur":
            enc = base64.b64encode(j["ref"].encode()).decode()
            url = ("https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/"
                   "v4/jobdetails/" + enc)
            req = urllib.request.Request(url, headers=BA_HDR)
            with urllib.request.urlopen(req, timeout=40) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            # 2 Oct 2026: the BA sends plain text with its own line breaks. They are kept now,
            # so a list stays a list.
            out["desc"] = html_to_text(d.get("stellenangebotsBeschreibung") or "")
            out["date"] = d.get("datumErsteVeroeffentlichung") or j.get("date", "")
            out["company"] = d.get("firma") or j["company"]
            out["remote"] = d.get("homeofficemoeglich")
            out["employment"] = d.get("angebotsart") or j.get("art", "")
            # 8 Sep 2026: the employer's own site, an external apply link when the employer
            # gave one, and the recruiter flags. The arbeitsagentur.de page sits behind a
            # captcha, so instructions/PROMPT.md section 3 resolves BA jobs to the employer's board and the
            # pack carries both. `istBetreut` means the Agentur itself manages applications.
            site = d.get("allianzpartnerUrl") or ""
            out["employer_site"] = ("https://" + site) if site and not site.startswith("http") else site
            out["externe_url"] = d.get("externeURL") or ""
            out["recruiter"] = bool(d.get("istPrivateArbeitsvermittlung")) or bool(d.get("istArbeitnehmerUeberlassung"))
            out["temp_agency"] = bool(d.get("istArbeitnehmerUeberlassung"))
            out["agentur_managed"] = bool(d.get("istBetreut"))
        elif j.get("desc"):
            out["desc"] = j["desc"]
        else:
            # 2 Oct 2026: scripts/jobpage.py reads the posting itself (ATS API, JSON-LD or the page's
            # main content). This used to be the whole page, menus included, cut at 9,000.
            r = jobpage.read(j["url"])
            out["desc"] = r.get("desc") or ("FETCH FAILED: %s" % r.get("error", "no text"))
    except Exception as e:
        out["desc"] = "FETCH FAILED: %s" % str(e)[:100]
    return out


if __name__ == "__main__":
    scratch = sys.argv[1]
    needles = [n.lower() for n in sys.argv[2:]]
    cands = json.load(open(os.path.join(scratch, "candidates.json")))
    picked = [c for c in cands if one.__doc__ or True]
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        res = [r for r in ex.map(one, cands) if r]

    for r in res:
        print("=" * 100)
        print("%s | %s" % (r["company"], r["title"]))
        print("loc=%s  date=%s  src=%s  remote=%s" %
              (r.get("location"), r.get("date"), r.get("source"), r.get("remote")))
        print("url=%s" % r.get("url"))
        if r.get("source") == "Bundesagentur":
            print("employer_site=%s  externe_url=%s  recruiter=%s  temp_agency=%s  agentur_managed=%s"
                  % (r.get("employer_site"), r.get("externe_url"), r.get("recruiter"),
                     r.get("temp_agency"), r.get("agentur_managed")))
        b, line = lang_band(r.get("desc") or "")
        print("band=%s  LANG: %s" % (b, line))
        full = r.get("desc") or ""
        # 29 Sep 2026: print without the benefits section and diversity boilerplate; pay, language and
        # location lines inside them are kept. The band above and the language lines below use the full text.
        d, cut = trim(full)
        if cut:
            print("(%d characters of benefits and boilerplate trimmed)" % cut)
        print(d[:5200])
        # 4 Sep 2026 evening: this used to print `desc[:5200]` and nothing else, which is
        # long enough for the intro and the responsibilities and almost never long enough
        # for the language line — German adverts put it last, in the closing bullet of the
        # profile block. Universitaetsklinikum Frankfurt's "Machine Learning Engineer -
        # Medical Imaging AI" was scored 8 and headed for the top slot off a truncated read;
        # the full 7,967-char text ends "Sehr gute Deutsch- und gute Englischkenntnisse" at
        # about char 6,800, a hard disqualification the printout had cut off. Same failure
        # mode as the 1 Sep and 4 Sep notes in instructions/PROMPT.md, one layer lower down: the read
        # was honest, the printer lied by omission. So always show the tail, and pull every
        # language sentence out explicitly so the bar cannot be missed wherever it sits.
        if len(d) > 5200:
            print("\n---- TAIL (chars %d-%d) ----" % (5200, len(d)))
            print(d[5200:])
        langs = re.findall(r"[^.\n*|]*(?:Deutsch|German|Englisch|English|Sprachkenntnis|"
                           r"verhandlungssicher|fluent|C1|C2|native)[^.\n*|]*", full, re.I)
        print("\n---- LANGUAGE LINES (%d) ----" % len(langs))
        for L in dict.fromkeys(s.strip() for s in langs if s.strip()):
            print("  * " + L[:300])
    print("\n--- %d read" % len(res), file=sys.stderr)
    json.dump(res, open(os.path.join(scratch, "read.json"), "w"), ensure_ascii=False)
