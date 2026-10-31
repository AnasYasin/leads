#!/usr/bin/env python3
"""Pull a stated salary out of a job description.

Only what the posting actually says. There is no estimate here and there must never
be one: an invented band is worse than no band, because he would negotiate against
it. `extract` returns "" when the posting is silent, which is most of the time.

German adverts write 70.000 - 90.000 EUR, English ones EUR 70,000-90,000 or 90k-120k,
and Ashby writes $140K – $175K. All of those come back normalised. A single number
only counts when a word like "up to" or "ab" makes it a band edge.

    python3 scripts/salary.py jobs/some-pack.md        one file
    python3 scripts/salary.py --show < description     the match and its sentence
"""

import re
import sys

# A salary is an annual figure in this range. Anything outside it is a headcount, a
# funding round or a user count, and those are exactly what a loose regex picks up.
MIN_YEAR, MAX_YEAR = 20_000, 400_000
MIN_HOUR, MAX_HOUR = 8, 200

CUR = r"(?:€|EUR|eur|Euro|\$|USD|CHF|£|GBP)"
NUM = r"\d{1,3}(?:[., \s]\d{3})+|\d{2,3}(?:[.,]\d)?\s?[kK]\b|\d{5,6}"
# The left side of a range may be bare, as in "EUR 90-120k" and "42-75k". It is scaled
# up to thousands below when the right side carries the k.
NUM_L = NUM + r"|\d{2,3}"
DASH = r"\s*(?:-|–|—|bis zu|bis|to|up to|und|and)\s*"

# Words that turn a number into something that is not pay. Checked in the 60 characters
# after the match, because "100.000 Kunden" and "€10M ARR" both look like a band.
NOT_PAY = re.compile(
    r"\b(nutzer|user|users|kunden|customers|mitarbeiter|employees|people|"
    r"arr|mrr|umsatz|revenue|funding|raised|valuation|downloads|mio|million|bn|billion|mrd|"
    r"budget|grant|zuschuss|market cap|marktkapitalisierung)\b",
    re.I,
)
# The slash form must sit right after a figure. Matching a bare "/h" read "VVC/H.266" in a
# Qualcomm advert as an hourly marker and threw away that posting's real annual band.
HOURLY = re.compile(
    r"\b(pro\s+stunde|per\s+hour|stundenlohn|hourly)\b|(?:\d|€|EUR)\s*/\s*(?:h|hr|hour|std)\b", re.I
)
MONTHLY = re.compile(r"\b(pro\s+monat|per\s+month|monatlich|/\s*(?:mo|month|monat))\b", re.I)
# Only used to prefer one match over another, never to reject one.
PAY_WORD = re.compile(
    r"\b(salary|salaries|compensation|comp|gehalt|gehalts\w*|verg[üu]tung|package|"
    r"base pay|pay range|jahresgehalt|bruttogehalt|brutto|p\.?a\.?|per annum|jährlich|"
    r"pro jahr|per year|annually|ote|festgehalt)\b",
    re.I,
)
ONE_SIDED = re.compile(r"\b(bis zu|up to|ab|from|starting at|starts at|mindestens|at least|"
                       r"ca\.?|circa|approx\.?|approximately|around|rund)\s*$", re.I)
# 29 Sep 2026. A single figure also counts when a pay label sits right in front of it:
# "Einstiegsgehalt : ca. 90.000 € Fixum" (FindYou), "Salary: €120k". And a figure in the
# advert's title line: "Agentic AI Architect - Berlin OR Remote | €120k" (Next Ventures),
# "Forward-Deployed AI Engineer - Claude Code - €120,000 - Munich" (Findr). All four were in
# sent packs with the salary field empty.
PAY_LABEL = re.compile(r"\b(salary|gehalt|einstiegsgehalt|jahresgehalt|festgehalt|fixum|verg[üu]tung|"
                       r"compensation|base|base salary|the deal)\s*[:=–-]?\s*(ca\.?|circa)?\s*$", re.I)
TITLE_SEP = re.compile(r"[|–—-]\s*$")
# German public pay scales name the band instead of a figure: "Entgelt entsprechend TV-L EG 13"
# (FZI), "Vergütung nach TVöD E 13". The scale is public, so the posting has stated its pay.
TARIFF = re.compile(r"\b(TV-?L|TV[öo]e?D(?:-Bund|-VKA)?|TV-?H|TV-?AVH)\b[^.\n]{0,40}?\b(?:E|EG|Entgeltgruppe)\s?(\d{1,2})\b"
                    r"|\b(?:Entgeltgruppe|EG)\s?(\d{1,2})\s+(TV-?L|TV[öo]e?D)\b", re.I)


def _n(tok):
    """'90k' -> 90000, '70.000' -> 70000, '140K' -> 140000."""
    t = tok.strip().lower().replace(" ", "").replace(" ", "")
    if t.endswith("k"):
        return int(float(t[:-1].replace(",", ".")) * 1000)
    return int(re.sub(r"[.,]", "", t))


def _fmt(lo, hi, period):
    unit = {"hour": " an hour", "month": " a month", "year": ""}[period]
    thousands = lo >= 1000 and lo % 1000 == 0 and (not hi or (hi >= 1000 and hi % 1000 == 0))
    if thousands:
        body = "%dk-%dk" % (lo // 1000, hi // 1000) if hi else "%dk" % (lo // 1000)
    else:
        body = "%s-%s" % (f"{lo:,}", f"{hi:,}") if hi else f"{lo:,}"
    return "EUR %s%s" % (body, unit)


def _plausible(lo, hi, period):
    lim = (MIN_HOUR, MAX_HOUR) if period == "hour" else (MIN_YEAR, MAX_YEAR)
    if period == "month":
        lim = (1_000, 40_000)
    for v in (lo, hi):
        if v and not (lim[0] <= v <= lim[1]):
            return False
    return not (hi and hi < lo)


def candidates(text):
    """Every plausible stated band in the text, best first."""
    t = re.sub(r"[  ]", " ", text or "")
    # "Salary: 85k euro - 160k euro" (WhyHireWrong?): a currency word between the first
    # figure and the dash breaks the range pattern. Move it out of the way.
    t = re.sub(r"(\d\s?[kK]?)\s*(?:€|euro|eur)\s*(?=(?:-|–|—|bis|to)\s*\d)", r"\1 ", t, flags=re.I)
    out = []

    # A range, with the currency on either side or on both.
    rng = re.compile(
        r"(?:(%s)\s*)?(%s)%s(?:(%s)\s*)?(%s)\s*(%s)?" % (CUR, NUM_L, DASH, CUR, NUM, CUR)
    )
    for m in rng.finditer(t):
        cur_before, a, cur_mid, b, cur_after = m.groups()
        if not (cur_before or cur_mid or cur_after or re.search(r"[kK]\b", m.group(0))):
            continue
        # Never start or stop inside a longer number. "$158,400.00 - $237,600.00" matched
        # from its ".00" once and reported a band of EUR 0 to 237,600.
        if m.start() and t[m.start() - 1] in "0123456789.,":
            continue
        tail = t[m.end(): m.end() + 60]
        if tail[:1].isdigit():
            continue
        if NOT_PAY.search(tail):
            continue
        try:
            lo, hi = _n(a), _n(b)
        except ValueError:
            continue
        # "90-120k" and "42-75k": the k on the right governs both sides.
        if lo < 1000 <= hi:
            lo *= 1000
        near = t[max(0, m.start() - 160): m.end() + 160]
        period = "hour" if HOURLY.search(near) else "month" if MONTHLY.search(near) else "year"
        if not _plausible(lo, hi, period):
            continue
        out.append((2 if PAY_WORD.search(near) else 1, m.start(), _fmt(lo, hi, period), m.group(0).strip(), near))

    # One number, but only when "up to" or "ab" makes it an edge of a band.
    one = re.compile(r"(?:(%s)\s*)?(%s)\s*(%s)?" % (CUR, NUM, CUR))
    for m in one.finditer(t):
        cur_before, a, cur_after = m.groups()
        if not (cur_before or cur_after or re.search(r"[kK]\b", m.group(0))):
            continue
        head = t[max(0, m.start() - 24): m.start()]
        # "Gewinnbeteiligung bis zu 24.000 €" (Böttcher AG) is a profit share, not pay.
        # Looks 60 characters back: "Gewinnbeteiligung bis zu " alone is 25 (review, 29 Sep 2026).
        if re.search(r"(gewinnbeteiligung|bonus|profit share|zuschuss|budget|pr[äa]mie)\w*(\W+\w+){0,3}\W*$",
                     t[max(0, m.start() - 60): m.start()], re.I):
            continue
        labelled = bool(PAY_LABEL.search(head))
        in_title = m.start() < 250 and bool(TITLE_SEP.search(head)) and bool(cur_before or cur_after)
        if not (ONE_SIDED.search(head.strip() + " " if head.strip() else "") or labelled or in_title):
            continue
        if NOT_PAY.search(t[m.end(): m.end() + 60]):
            continue
        try:
            lo = _n(a)
        except ValueError:
            continue
        near = t[max(0, m.start() - 160): m.end() + 160]
        period = "hour" if HOURLY.search(near) else "month" if MONTHLY.search(near) else "year"
        if not _plausible(lo, 0, period):
            continue
        if period == "year" and lo < 40_000 and (labelled or in_title):
            continue
        if re.search(r"(bis zu|up to)\s*$", head, re.I):
            edge = "up to "
        elif re.search(r"(ca\.?|circa|approx\.?|approximately|around|rund)\s*$", head, re.I):
            edge = "about "
        elif re.search(r"(ab|from|starting at|starts at|mindestens|at least)\s*$", head, re.I):
            edge = "from "
        else:
            edge = ""
        out.append((2 if (PAY_WORD.search(near) or labelled) else 1 if in_title else 0, m.start(),
                    edge + _fmt(lo, 0, period), m.group(0).strip(), near))

    # An hourly or monthly rate is stated as one number, with no "up to" in front of it.
    # "18 EUR pro Stunde" is the shape, and it is how the side-job adverts quote pay.
    # NUM first, so "4.500" reads as four and a half thousand and not as the decimal 4.50.
    rate = re.compile(r"(?:(%s)\s*)?(%s|\d{1,3}(?:[.,]\d{1,2})?)\s*(%s)?" % (CUR, NUM, CUR))
    for m in rate.finditer(t):
        if not (m.group(1) or m.group(3)):
            continue
        near = t[max(0, m.start() - 60): m.end() + 60]
        period = "hour" if HOURLY.search(near) else "month" if MONTHLY.search(near) else ""
        if not period:
            continue
        try:
            lo = _n(m.group(2)) if not re.match(r"^\d{1,3}[.,]\d{1,2}$", m.group(2).strip()) \
                else int(float(m.group(2).replace(",", ".")))
        except ValueError:
            continue
        if not _plausible(lo, 0, period):
            continue
        out.append((2, m.start(), _fmt(lo, 0, period), m.group(0).strip(), near))

    for m in TARIFF.finditer(t):
        scale = (m.group(1) or m.group(4) or "").upper().replace("TVOED", "TVöD").replace("TVOD", "TVöD").replace("TVÖD", "TVöD")
        grade = m.group(2) or m.group(3)
        out.append((0, m.start(), "%s E%s (public pay scale)" % (scale, grade), m.group(0).strip(),
                    t[max(0, m.start() - 80): m.end() + 80]))

    out.sort(key=lambda r: (-r[0], r[1]))
    return out


# What to ask for when the posting states no figure. the candidate's rule, 29 Sep 2026. This is never
# shown as the posting's salary; it is his opening number, labelled as his rule.
ASK = {
    # <fill at setup: the candidate's opening figure per company size, e.g. "EUR 55-60k". An empty
    # figure prints no Ask line for that class.>
    "startup": ("", "your rule for a startup or small company, under 50 staff"),
    "mid": ("", "your rule for a mid-size company, 50 to 1,000 staff"),
    "large": ("", "your rule for a large corporation, 1,000+ staff"),
    "public": ("", "your rule for public sector and research"),
    "recruiter": ("the range, from the recruiter first", "client not named; once you know the client, use its size"),
}


def ask(size_class, stated=""):
    """(figure, why) to ask for, or ("", "") when the posting states pay or the class is unknown."""
    if str(stated or "").strip():
        return "", ""
    fig, why = ASK.get((size_class or "").strip().lower(), ("", ""))
    return (fig, why) if fig else ("", "")


def extract(text):
    c = candidates(text)
    return c[0][2] if c else ""


def numbers(s):
    """The thousands in a salary string, for comparing two of them."""
    vals = set()
    for m in re.finditer(r"(\d{1,3}(?:[.,]\d{3})+|\d{2,3}k|\d{4,6})", (s or "").lower()):
        try:
            vals.add(round(_n(m.group(1)) / 1000))
        except ValueError:
            pass
    return vals


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show = "--show" in sys.argv[1:]
    text = open(args[0], encoding="utf-8", errors="replace").read() if args else sys.stdin.read()
    c = candidates(text)
    if not c:
        print("")
        return 1
    print(c[0][2])
    if show:
        print("  matched: %s" % c[0][3], file=sys.stderr)
        print("  context: ...%s..." % " ".join(c[0][4].split()), file=sys.stderr)
        for r in c[1:4]:
            print("  also: %s (%s)" % (r[2], r[3]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
