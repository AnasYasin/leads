#!/usr/bin/env python3
"""Order candidates.json so the run reads the likeliest jobs first.

Added 29 Sep 2026. A run has 600 to 900 candidates after the filters and reads about 45 in
full, in freshness order. This gives every candidate a cheap score from the title, the
description when the row has one, and the date, and filter_run.py sorts by it. It never drops
a row. A low score only means the row is read later, and an unread row comes back next run.

The terms come from instructions/PROFILE.md: target roles, tools he has really used, not-wanted roles and
the seniority rule. `why` lists what moved the score, so the order can be checked by eye.

    python3 scripts/prescore.py <scratch>     print candidates.json in score order
"""
import datetime, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402

# Every term and weight is read from config/radar.yaml, section prescore (29 Sep 2026).
P = cfg.get("prescore")

# Title. Computer vision and audio are the main focus (instructions/PROFILE.md, 8 Sep 2026).
# Checked 29 Sep 2026 on that night's pool: "Elektroniker ... Audio", "IT-Techniker
# Audio-/Videoausstattung" and an audiometrist all took +4 from a bare "audio" or "video". The
# generic words now count only next to an ML word; the specific phrases count on their own.
ML_WORD = cfg.pattern(P["ml_word"])
T_SPECIFIC = cfg.pattern(P["title_specific"])
# Word boundaries, so "division", "supervision", "revision" and "simulation" do not count (review).
T_GENERIC = cfg.pattern(P["title_generic"])
T_PLUS = [(x["points"], cfg.pattern(x["pattern"])) for x in P["title_plus"]]
T_MINUS = [(x["points"], cfg.pattern(x["pattern"])) for x in P["title_minus"]]
# Description. Distinct matches only, so a posting cannot win by repeating one word.
D_PLUS = cfg.patterns(P["desc_plus"])
D_MINUS = [(x["points"], cfg.pattern(x["pattern"])) for x in P["desc_minus"]]


INFRA = cfg.patterns(P["infra"])


def _date(j):
    d = (j.get("date") or "")[:10]
    try:
        return datetime.date.fromisoformat(d)
    except ValueError:
        return None


def desc_points(d):
    """What the description adds to the score, on its own."""
    d = (d or "").lower()
    s = min(len([p for p in D_PLUS if re.search(p, d)]), P["desc_plus_cap"])
    if len([p for p in INFRA if re.search(p, d)]) >= P["infra_min"]:
        s += P["infra_points"]
    return s + sum(w for w, pat in D_MINUS if re.search(pat, d))


def score(j, today=None, no_desc=1):
    today = today or datetime.date.today()
    t = (j.get("title") or "").lower()
    # The company's own name inside the title is not a job word: "Director Information Security,
    # the referral company Data & AI" is not an AI role. Remove it before matching.
    co = (j.get("company") or "").lower().strip()
    if len(co) >= 4:
        t = t.replace(co, " ")
    d = (j.get("desc") or "").lower()
    s, why = 0, []
    title_hit = 0
    m = re.search(T_SPECIFIC, t) or (re.search(ML_WORD, t) and re.search(T_GENERIC, t))
    if m:
        title_hit = P["title_specific_points"]
        why.append("+%d %s" % (title_hit, m.group(0)))
    else:
        for w, pat in T_PLUS:
            if re.search(pat, t):
                title_hit = w
                why.append("+%d %s" % (w, re.search(pat, t).group(0)))
                break                  # the best title match only; titles stack words
    s += title_hit
    for w, pat in T_MINUS:
        if re.search(pat, t):
            s += w
            why.append("%d %s" % (w, re.search(pat, t).group(0)))
    if d:
        hits = [p for p in D_PLUS if re.search(p, d)]
        s += min(len(hits), P["desc_plus_cap"])
        if hits:
            why.append("+%d desc" % min(len(hits), P["desc_plus_cap"]))
        infra = [p for p in INFRA if re.search(p, d)]
        if len(infra) >= P["infra_min"]:
            s += P["infra_points"]
            why.append("%+d infra core (%s)" % (P["infra_points"], len(infra)))
        for w, pat in D_MINUS:
            if re.search(pat, d):
                s += w
                why.append("%d %s" % (w, re.search(pat, d).group(0)))
    elif title_hit:
        # LinkedIn and BA rows carry no description here. They get the median description score
        # of this run's described rows, so they sit among the rest, and only for a title that
        # matched a target role. It was a flat +3 until the review of 29 Sep 2026 measured the
        # real median at 1: 43 of the top 45 rows were cards, and Helsing's AI Research Engineer
        # sat at #52.
        s += no_desc
        why.append("%+d no desc" % no_desc)
    dt = _date(j)
    if dt:
        age = (today - dt).days
        f = next((b["points"] for b in P["freshness"] if age <= b["max_days"]), P["freshness_older_points"])
        if f:
            s += f
            why.append("%+d age %dd" % (f, age))
    # LinkedIn's window is 24 hours, so an unread LinkedIn row read twice late is gone.
    src_pts = P["source_bonus"].get(j.get("source") or "", 0)
    if src_pts:
        s += src_pts
        why.append("%+d %s" % (src_pts, j.get("source")))
    for city, pts in P["location_bonus"].items():
        city = str(city).lower()            # the location is compared lower-cased (review, 29 Sep 2026)
        if city and city in (j.get("location") or "").lower():
            s += pts
            why.append("%+d %s" % (pts, city))
    if j.get("referral") and (title_hit >= P["referral_min_title_points"] or re.search(
            cfg.pattern(P["referral_title"]), t)):
        # instructions/PROFILE.md: the referral company roles with real ML content only. "Director Information Security"
        # took this bonus on 29 Sep before the title condition.
        s += P["referral_points"]
        why.append("%+d referral" % P["referral_points"])
    return s, why


def fresh_group(j, today=None):
    """0 for a job posted within the first `reading.fresh_first_days` limit, 1 within the second, and so
    on; the last group holds older and undated jobs."""
    today = today or datetime.date.today()
    limits = cfg.get("reading", "fresh_first_days")
    d = _date(j)
    if d is None:
        return len(limits)
    age = (today - d).days
    return next((i for i, lim in enumerate(limits) if age <= lim), len(limits))


def order(cands, today=None):
    """Freshest first, then by prescore (30 Sep 2026). Before, freshness was worth one or two points
    and a job posted that morning could sit below weeks-old jobs with a better title: on 29 Sep
    Brainlab's Applied AI Engineer, posted that day, ranked 66th and was never read."""
    pts = sorted(desc_points(j.get("desc")) for j in cands if j.get("desc"))
    med = pts[len(pts) // 2] if pts else 1
    for j in cands:
        j["prescore"], j["prescore_why"] = score(j, today, no_desc=med)
    return sorted(cands, key=lambda j: (fresh_group(j, today), -j["prescore"]))


if __name__ == "__main__":
    c = json.load(open(os.path.join(sys.argv[1], "candidates.json")))
    for j in order(c):
        print("%4d  %-26s | %-55s | %-9s | %s" % (j["prescore"], (j.get("company") or "")[:26],
                                              (j.get("title") or "")[:55], j.get("source", "")[:9],
                                              ", ".join(j["prescore_why"])))
