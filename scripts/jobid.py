#!/usr/bin/env python3
"""Job identity for `state/seen.json`, hardened after the 5 August 2026 morning run.

That run shortlisted eight jobs and six of them turned out to be repeats. The
exact-id match missed every one, because the id is built from strings that the
sources spell differently on different days:

  "HZDR (Helmholtz-Zentrum Dresden-Rossendorf)"   vs  "Helmholtz-Zentrum Dresden-Rossendorf"
  "Mercedes-Benz Group"                           vs  "Mercedes-Benz Group AG"
  "Wissenschaftliche*r Mitarbeiter*in / PhD"      vs  "Wissenschaftliche/r Mitarbeiter/in / PhD Student (m/w/d)"
  "AI Engineer (f/m/x)"                           vs  "AI Engineer (f/m/x) - Berlin - Hybrid"

So `canonical_id` is not enough on its own. Use `is_repeat`, which takes the id
first and then falls back to a company-plus-title-overlap check. Exact ids stay
in `state/seen.json` for the record; the fuzzy pass is what actually protects the email.
"""

import json
import re
import unicodedata

# Gender and seniority markers, and the parenthetical noise around them.
GENDER = re.compile(
    r"\(\s*[mwfdxa](\s*[/|,]\s*[mwfdxa])+\s*\)"          # (m/w/d), (f/m/x), (w/m/div.)
    r"|\(\s*all\s+genders?\s*\)|\(\s*gn\s*\)|\(\s*d\s*\)"
    r"|[*:_/]innen|[*:_/]in\b"                            # Doktorand*in, Mitarbeiter:in
    r"|\bm\s*/\s*w\s*/\s*d\b|\bf\s*/\s*m\s*/\s*[xd]\b|\bw\s*/\s*m\s*/\s*d\b"
    r"|\bd\s*/\s*f\s*/\s*m\b|\bf_m_x\b|\bdiv\.?\b",
    re.I,
)
SENIORITY = re.compile(
    r"\b(senior|junior|sr|jr|lead|principal|staff|head|werkstudent|"
    r"praktikant|intern|trainee|associate)\b"
    # 29 Oct 2026: SumUp retitled Greenhouse 8498275002 from "Senior Machine Learning Engineer I" to
    # "AI / Machine Learning Engineer II" and the talent.com copy carried no Greenhouse link. A roman
    # level is seniority, like "senior".
    r"|\b(?:i{1,3}|iv)\b",
    re.I,
)
# Legal-form suffixes that appear and disappear between boards.
# The public-body forms on the second line matter as much as the commercial ones:
# on 28 August 2026 the Bundesagentur shipped the Hildesheim ISMLL PhD as
# "Stiftung Universität Hildesheim" while `state/seen.json` held it as
# "Universität Hildesheim (ISMLL)". `stiftung` survived normalisation, diluted the
# token set, and the role — sent the previous evening at fit 8 — came back as new.
LEGAL = re.compile(
    r"\b(gmbh|ag|se|kg|mbh|co|ug|e\.?\s?v|gemeinnuetzige|ggmbh|group|"
    r"holding|inc|ltd|llc|bv|nv|oy|ab|as|sa|srl|spa|plc|university|"
    r"universitaet|hochschule|institut|zentrum|"
    r"stiftung|kdoer|koerperschaft|anstalt|landesbetrieb)\b",
    re.I,
)
# 28 Sep 2026: the Bundesagentur shipped Jülich's role as "Forschungszentrum Jülich GmbH P-VA
# Personalabrechnung", the payroll office that filed it. The two extra tokens took the overlap
# with the sent "Forschungszentrum Jülich (Jülich Supercomputing Centre)" under 0.6.
ADMIN = re.compile(r"\bp[\s-]?va\b|\bpersonal(abrechnung|abteilung|service|wesen|verwaltung)\b", re.I)
STOP = {"the", "a", "an", "of", "and", "in", "at", "for", "to", "with",
        "und", "der", "die", "das", "den", "dem", "im", "fuer", "bei",
        "als", "zur", "zum", "bereich", "team", "m", "w", "d", "f", "x",
        # Agency boilerplate. We spell recruiter rows "<Agency> (recruiter,
        # client not named)", and company_tokens keeps bracket contents on
        # purpose, so without these every agency matched every other one on
        # the shared {client, not, named} and prior sends were cross-reported.
        "client", "clients", "named", "not", "end", "recruiter", "agency"}
# Boards tack the city and the work mode onto the title. The Bundesagentur ships
# NETCONOMY's role as "AI Engineer (f/m/x) - Berlin - Hybrid" while the company's
# own board calls it "AI Engineer (f/m/x)". Strip these before comparing.
PLACE = {"berlin", "muenchen", "munich", "hamburg", "koeln", "cologne",
         "frankfurt", "stuttgart", "duesseldorf", "leipzig", "dresden",
         "hannover", "nuernberg", "nuremberg", "bremen", "karlsruhe",
         "heidelberg", "darmstadt", "bonn", "aachen", "muenster", "mannheim",
         "freiburg", "potsdam", "jena", "ilmenau", "tuebingen", "regensburg",
         "ulm", "kassel", "magdeburg", "augsburg", "mainz", "wien", "vienna",
         "graz", "dortmund", "essen", "sindelfingen", "gilching", "germany",
         # European cities, 29 Sep 2026: Briink's title came back as "... @Briink Berlin, London"
         # and "london" diluted the title match.
         "london", "paris", "amsterdam", "madrid", "barcelona", "lisbon", "lissabon", "dublin",
         "zurich", "zuerich", "warsaw", "warschau", "prague", "prag", "milan", "mailand", "rome",
         "stockholm", "copenhagen", "oslo", "helsinki", "brussels", "bruessel", "ingolstadt",
         "wolfsburg", "erlangen", "garching", "unterschleissheim", "europe", "emea", "eu",
         "deutschland", "hybrid", "remote", "onsite", "office", "standort"}


def fold(s):
    """Lowercase, strip accents, collapse to alphanumeric tokens."""
    s = (s or "").lower()
    s = (s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
          .replace("ß", "ss").replace("æ", "ae").replace("ø", "oe"))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# German public-sector pay bands and workload quotas ride along on university and
# public-body titles and differ between the employer's own advert and the copy the
# Bundesagentur carries. On 28 August 2026 the Hildesheim ISMLL PhD arrived as
# "PhD Position in Machine Learning (m/f/d) - TV-L E 13, 100%" against a `state/seen.json`
# entry of "PhD Position in Machine Learning (m/f/d)"; the five extra tokens diluted
# the overlap enough that a role sent the previous evening scored as new.
PAYBAND = re.compile(
    r"\b(?:tv[-\s]?(?:l|oe?d|h|n)|entgeltgruppe|besoldungsgruppe|"
    r"verguetungsgruppe|vergütungsgruppe)\b[^,;|)]*"
    r"|\b\d{1,3}\s?%",
    re.I,
)


# 28 Sep 2026, two repeats that reached a run as new. StepStone titled GEMA's role
# "AI Engineer (m/w/d) - Vor Ort" against a sent "AI Engineer (m/w/d)", and talent.com titled
# handly's "Founding AI Engineer @handly - 20VC backed" against a sent "Founding AI Engineer".
# Work-mode phrases, an "@company" mention and an "<investor> backed" tag carry no job content.
TITLE_NOISE = re.compile(
    r"@\s*[\w.\-]+|\b[\w.\-]+[\s-]backed\b|\bvor[\s-]ort\b|\bon[\s-]site\b|\bhome[\s-]?office\b"
    r"|\bmobiles?\s+arbeiten\b|\bgesucht\b",
    re.I,
)
# 29 Oct 2026, from docs/CODE_ISSUES.md. HUK-COBURG's Bundesagentur title opened "Wir suchen: (Senior)
# Engineer ..." and ELAC SONAR's talent.com title ended " - LLMs & On-Premises gesucht"; both came back
# as new beside the plain title. A lead-in and a trailing "wanted" segment say nothing about the job.
LEADIN = re.compile(
    r"^\s*(?:(?:wir suchen|we are looking for|we're looking for|we are hiring|we're hiring)\b\s*:?"
    r"|(?:gesucht|stellenangebot|stellenanzeige|stellenausschreibung|jobangebot|job)\s*:)"
    r"\s*(?:(?:an?|einen?|eine|the|unseren?|unsere)\b\s*)?",
    re.I,
)
GESUCHT_TAIL = re.compile(r"\s*[-–—|·:,(]\s*[^–—|·]*\bgesucht\b[^–—|·]*$", re.I)


def _title_tokens(t):
    t = re.sub(r'["“”„\']', " ", t or "")
    t = GESUCHT_TAIL.sub(" ", LEADIN.sub("", t + " ").rstrip())
    t = TITLE_NOISE.sub(" ", t)
    t = PAYBAND.sub(" ", t)
    t = SENIORITY.sub(" ", t)
    return [w for w in fold(t).split() if w not in STOP and w not in PLACE]


def norm_title(t):
    """Normalise a job title for comparison.

    Parentheticals are dropped, because boards stuff gender tags, percentages and work
    modes in there — "PhD Candidate (65%, m/f/x)", "AI Engineer (f/m/x) - Berlin - Hybrid".

    But dropping them unconditionally destroys titles where the parenthetical carries the
    *only* distinguishing content. Every poolside posting is "Member of Engineering
    (<specialty>)"; stripping the bracket collapses Evaluations, Post-training,
    Pre-training and Multimodality into one job, and on 8 Aug 2026 `is_repeat` duly
    declared the second poolside role a repeat of the first. So: strip, and if what is
    left is too thin to identify a job on its own, put the bracket contents back.
    """
    stripped = _title_tokens(re.sub(r"\([^)]*\)", " ", GENDER.sub(" ", t or "")))
    if len(stripped) >= 3:
        return " ".join(stripped)
    return " ".join(_title_tokens(GENDER.sub(" ", t or "")))


def norm_company(c):
    c = GENDER.sub(" ", ADMIN.sub(" ", c or ""))
    c = re.sub(r"\([^)]*\)", " ", c)          # "HZDR (Helmholtz-Zentrum ...)" -> "HZDR"
    toks = [w for w in fold(c).split() if w not in STOP]
    core = [w for w in toks if not LEGAL.fullmatch(w)]
    return " ".join(core or toks)


def company_tokens(c):
    """Both the bracketed and unbracketed readings, so either spelling matches."""
    raw = fold(GENDER.sub(" ", ADMIN.sub(" ", c or ""))).split()
    out = {w for w in raw if not LEGAL.fullmatch(w) and w not in STOP}
    return out or set(raw)


def _squash(c):
    """The company name with every separator removed.

    Token-set comparison cannot see that "NextexAI" and "NexTex AI" are one
    employer: the first folds to {nextexai}, the second to {nextex, ai}, and the
    sets do not intersect at all. That let NexTex AI's Founding Computer Vision /
    Machine Learning Engineer — sent 29 July 2026 at fit 9 — come back as new on
    10 August. Boards disagree about internal spacing and camel-casing constantly
    ("BlackForestLabs" / "Black Forest Labs", "SpAItial" / "Sp AItial"), so
    compare the separator-free spelling as well as the token sets.
    """
    return "".join(w for w in fold(GENDER.sub(" ", ADMIN.sub(" ", c or ""))).split()
                   if not LEGAL.fullmatch(w) and w not in STOP)


def canonical_id(company, title, location=""):
    parts = [norm_company(company).replace(" ", "-"),
             norm_title(strip_company_affix(title, company)).replace(" ", "-"),
             fold(location).replace(" ", "-")]
    return "-".join(p for p in parts if p)


def _initials(c):
    return "".join(w[0] for w in fold(GENDER.sub(" ", c or "")).split())


def _acronym_match(a, b):
    """"MPI für Astronomie" is the same employer as "Max-Planck-Institut für
    Astronomie", and token overlap alone cannot see it. Match when one side is a
    single short token that opens the other side's initials."""
    for x, y in ((a, b), (b, a)):
        toks = [w for w in fold(GENDER.sub(" ", x or "")).split() if w not in STOP]
        short = [w for w in toks if 2 <= len(w) <= 5]
        ini = _initials(y)
        if ini and any(len(w) >= 2 and ini.startswith(w) for w in short):
            return True
    return False


def same_company(a, b):
    ta, tb = company_tokens(a), company_tokens(b)
    if not ta or not tb:
        return False
    # Separator-free spelling first: catches "NextexAI" vs "NexTex AI", which
    # share no tokens at all. Require 6+ characters so that short squashes like
    # "ai" or "ml" cannot swallow every company that starts with them.
    sa, sb = _squash(a), _squash(b)
    if sa and sb and min(len(sa), len(sb)) >= 6 and (sa == sb or sa.startswith(sb) or sb.startswith(sa)):
        return True
    if ta <= tb or tb <= ta:
        return True
    if len(ta & tb) / min(len(ta), len(tb)) >= 0.6:
        return True
    return bool(ta & tb) and _acronym_match(a, b)


def strip_company_prefix(title, company):
    """Drop a leading "<employer>:" from a title.

    The Bundesagentur ships some employers' postings with the full legal company name
    glued to the front of the title: "GlobalFoundries Management Services GmbH & Co. KG:
    Machine Learning Engineer for Digital Manufacturing", where the company's own board
    and `state/seen.json` both say "Machine Learning Engineer for Digital Manufacturing". The
    prefix adds five tokens of pure noise, which drags the Jaccard in `same_title` under
    0.75 and lets the repost through as new. That happened on 13 August 2026 to a role
    sent on 28 July at fit 8 — it would have been the top of that morning's email.

    Strip only when the text before the colon really is the employer, checked with
    `same_company`. Titles legitimately carry colons — "Masterarbeit: Agentisches
    KI-System …", "PhD Thesis: Applying Satellite-Based Remote Sensing …" — and cutting
    those would throw away the only identifying content in the title.
    """
    m = re.match(r"^([^:]{2,80}):\s*(.+)$", (title or "").strip())
    if not m:
        return title
    head, rest = m.group(1), m.group(2)
    if len(_title_tokens(rest)) >= 2 and same_company(head, company):
        return rest
    return title


def strip_company_suffix(title, company):
    """Drop a trailing "- <employer>" from a title.

    The mirror image of `strip_company_prefix`, and the same failure. talent.com appends
    the employer to the title — "Senior Machine Learning Engineer (m/w/d) - PDR.cloud
    GmbH", where PDR.cloud's own listing and `state/seen.json` both say "Senior Machine
    Learning Engineer (all genders)". The two extra tokens drag the Jaccard in
    `same_title` from 1.0 down to 0.6, and on 25 August 2026 morning that let a job
    sent the previous evening back through as new — it survived only because the run
    re-checked the shortlist by hand, which is exactly what instructions/PROMPT.md section 5 asks for.

    Same guard as the prefix version: cut only when the tail really is the employer, and
    only when enough of a title survives. Titles carry trailing dashes for real content
    too — "AI Engineer (f/m/x) - Berlin - Hybrid" is handled by PLACE, but "Research
    Scientist - World Models" must keep its tail.
    """
    m = re.match(r"^(.+?)\s*[-–—|·]\s*([^-–—|·]{2,80})$", (title or "").strip())
    if not m:
        return title
    rest, tail = m.group(1), m.group(2)
    if len(_title_tokens(rest)) >= 2 and same_company(tail, company):
        return rest
    return title


def strip_company_affix(title, company):
    """Both ends, in one call."""
    return strip_company_suffix(strip_company_prefix(title, company), company)


def _heal_truncation(xs, ys):
    """Repair a trailing token that a source cut off mid-word.

    The Bundesagentur truncates the job title at 100 characters, and because it also
    prefixes the title with the employer's legal name (see `strip_company_prefix`) the
    cut usually lands inside the last real word. On 13 August 2026 GlobalFoundries'
    "…Machine Learning Engineer for Digital Manufacturi" failed to match the stored
    "Machine Learning Engineer for Digital Manufacturing" on that single clipped token:
    four shared tokens over a union of six is 0.67, under the 0.75 threshold, so a role
    sent on 28 July came back as new at fit 8.

    So: if the last token of one title is absent from the other but is a strict prefix of
    the other's last token, treat the two as the same word. Three guards keep this from
    fusing genuinely different jobs — the stem must be 4+ characters, and the match must
    sit at the end of *both* titles, which is what truncation actually looks like. Without
    that last condition "Machine Learning Engineer" heals into "Machine Learning
    Engineering Manager" and suppresses a real second opening.
    """
    if not xs or not ys or xs[-1] in set(ys) or len(xs[-1]) < 4:
        return xs
    return xs[:-1] + [ys[-1]] if ys[-1].startswith(xs[-1]) else xs


def same_title(a, b):
    """Jaccard, not containment.

    Containment is what made this too loose: ML6's "Senior AI Engineer" folds to
    {ai, engineer}, which is a subset of "AI Platform Engineer - Enterprise
    Intelligence" and matched a genuinely different job. Jaccard over the union
    at 0.75 separates those while still catching the real repeats, because the
    city and gender noise has already been stripped above.
    """
    la, lb = norm_title(a).split(), norm_title(b).split()
    la, lb = _heal_truncation(la, lb), _heal_truncation(lb, la)
    ta, tb = set(la), set(lb)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.75


def same_role(a, b, company="", loose=False):
    """Is title b the same role as title a, allowing for his own edits in state/applications.md?

    Review of 29 Sep 2026 on real rows. the candidate edits titles when he logs them: "Senior Machine
    Learning Engineer - (Logistics, Optimization)" became "..., Logistics Optimization", "Senior AI
    Software Engineer" became "..., req 11563", "Data Scientist (w/m/d)" became "... - 7641". At the
    0.75 bar none of those matched. But a loose token overlap made TACTILIA "Imitation Learning"
    restamp the applied "Reinforcement Learning" row.

    strict (loose=False): same_title, or one title contains the other and the extra words are only
      numbers, reference ids or the company's own name. Used where a wrong match rewrites a row.
    loose: same_title, or either title's words contain the other's, or Jaccard >= 0.5. Used where a
      wrong match only keeps something, as in the prune guard.
    """
    if same_title(a, b):
        return True
    ta = set(norm_title(strip_company_affix(a, company)).split())
    tb = set(norm_title(strip_company_affix(b, company)).split())
    if not ta or not tb:
        return False
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if loose:
        return (len(small) >= 2 and small <= big) or len(ta & tb) / len(ta | tb) >= 0.5
    if len(small) < 2 or not small <= big:
        return False
    extra = big - small
    co = company_tokens(company)
    return all(re.fullmatch(r"[a-z]*\d[\w-]*|req|id|ref|nr|no", w) or w in co for w in extra)


# 29 Oct 2026: get-in-it.de appends its category list to the title. Parship went into state/seen.json
# from a talent.com copy as "(Junior) Machine Learning Engineer (all genders) - Anwendungsentwicklung,
# Ingenieur" and the Bundesagentur's plain title scored 0.6. Only entries that carry a get-in-it link
# lose the tail, and only a tail of capitalised single words, so "Research Scientist - World Models"
# and "- GeoAI for Humanitarian Applications" stay whole.
_CATEGORY_TAIL = re.compile(r"^(.+?)\s*[-–—|]\s*([A-ZÄÖÜ][\wäöüß-]+(?:,\s*[A-ZÄÖÜ][\wäöüß-]+){0,3})\s*$")


def strip_board_tail(title, links):
    if not any("get-in-it.de" in (u or "") for u in links):
        return title
    m = _CATEGORY_TAIL.match((title or "").strip())
    return m.group(1) if m and len(_title_tokens(m.group(1))) >= 2 else title


def title_in_desc(sent_title, title, desc, head=1500):
    """True when the sent title stands in the opening of this row's text, in order, at most three
    words between its tokens, and the two titles share two tokens.

    29 Oct 2026, two LinkedIn cards whose title was not the advert's own. Hornetsecurity's "Data
    Engineer" opened "Wir suchen ... einen Data Engineer/Software Engineer (m/w/d)", the role sent on
    2 Oct under that title. HeiGIT's "Data Engineer - Machine Learning (m/f/d)" said "We are looking
    for a Senior Machine Learning Engineer, with focus on GeoAI for Humanitarian Applications", sent
    22 Oct under that title. Called only after same_company, so the two-token overlap keeps "Head of
    AI" from matching a sent "Machine Learning Engineer" named in its text."""
    toks = norm_title(sent_title).split()
    if len(toks) < 3 or len(set(toks) & set(norm_title(title).split())) < 2 or not desc:
        return False
    pat = r"\b" + r"\b(?:\s+\w+){0,3}?\s+\b".join(re.escape(w) for w in toks) + r"\b"
    return re.search(pat, fold(LINKEDIN_FOOTER.sub(" ", desc)[:head])) is not None


def _title_words(t):
    t = SENIORITY.sub(" ", GENDER.sub(" ", t or ""))
    return {w for w in fold(t).split() if len(w) >= 3 and w not in STOP and w not in PLACE and not w.isdigit()}


def second_opening(url, title, match, pool_urls):
    """True when `match` (a sent job is_repeat returned) and this row are two openings at once.

    Both links are live in this run's pool (pool_urls, normalised), they differ on the same host,
    and the titles differ by a real word. Seniority, gender tags, places and numbers do not count:
    "(Senior) Data Scientist" next to "Data Scientist", or the same title under a second link, is one
    job for the candidate. Brackets do count, because Preply's two roles differ only inside one: "(AI
    Learning)" and "(AI Marketplace)". Used by filter_run.py and by final_check.py, so the filter and
    the final check cannot disagree: on 29 Sep a hand-run is_repeat on the final list dropped the two
    second openings the filter had let through, and the morning email went out twice.
    """
    u = norm_url(url)
    links = _links(match)
    if not u or u in links or not any(x in pool_urls and _host(x) == _host(u) for x in links):
        return False
    a, b = _title_words(title), _title_words(match.get("title"))
    return bool(a ^ b) and any(len(w) >= 4 for w in a ^ b)


# A url only identifies a job when it points at that one job. Some employers have no
# per-job urls at all — microagi publishes every opening on the single JavaScript careers
# page `microagi.ai/careers`, so each role gets stored under that same url. The url branch
# below then matched every *future* microagi role against the first one ever sent, and on
# 13 August 2026 evening it hid four genuinely new Munich research roles (Depth Research
# Engineer, SLAM Research Engineer, Research Engineer (Post-Training / RL), Researcher)
# behind "Research Scientist (Robotics / AI)", sent 8 August. Same trap for any careers
# index reached through an aggregator.
_INDEX_URL = re.compile(
    r"^https?://[^/]+/?(?:[a-z]{2}/)?(?:careers?|jobs?|stellen|karriere|vacancies|"
    r"open-positions?|join-us|company/careers?)/?$", re.I)


def _ambiguous_urls(seen):
    """Urls in `seen` that cannot identify a single job: careers indexes, and any url
    already shared by two entries whose titles are genuinely different."""
    by_url = {}
    for e in seen:
        u = norm_url(e.get("url") or "")
        if u:
            by_url.setdefault(u, []).append(e.get("title", ""))
    bad = set()
    for u, titles in by_url.items():
        if _INDEX_URL.match(u):
            bad.add(u)
        elif len(titles) > 1 and any(not same_title(titles[0], t) for t in titles[1:]):
            bad.add(u)
    return bad


def _host(u):
    m = re.match(r"^https?://([^/]+)", u or "", re.I)
    if not m:
        return ""
    h = m.group(1).lower()
    return h[4:] if h.startswith("www.") else h


CITY_ALIAS = {"munich": "muenchen", "cologne": "koeln", "nuremberg": "nuernberg", "vienna": "wien"}
NOT_A_CITY = {"germany", "deutschland", "hybrid", "remote", "onsite", "office", "standort"}


def _cities(s):
    return {CITY_ALIAS.get(w, w) for w in fold(s or "").split() if w in PLACE and w not in NOT_A_CITY}


def same_place(a, b):
    """True when two location strings name at least one city in common, or either is
    blank. Deliberately loose — boards write "Berlin", "Berlin, BERLIN" and
    "LiveEO GmbH Berlin Office (Hybrid)" for the same place.

    Review, 29 Sep 2026: München and Munich were different places, and "germany" or "hybrid"
    counted as a city, so "Coburg, Bayern (hybrid...)" did not match "Coburg, Bavaria, Germany"."""
    ta, tb = _cities(a), _cities(b)
    if not ta or not tb:
        return True
    return bool(ta & tb)


def same_title_loose(a, b):
    """Jaccard at 0.6 instead of 0.75. Only safe in the narrow case in `is_repeat`.

    0.6 is not arbitrary — the two real cases bracket it and there is no room to be
    sloppier. Sikia's one job under two titles ("Founding Engineer - Applied AI
    Engineering & Full-Stack" vs "Founding Engineer (Applied AI / Backend Engineering)")
    scores 0.625 and must match. microagi's two genuinely different openings on one
    careers page ("Depth Research Engineer" vs "SLAM Research Engineer") score exactly
    0.5 and must not. Anything at or below 0.6 reopens the microagi bug of 13 Aug 2026.
    """
    la, lb = norm_title(a).split(), norm_title(b).split()
    la, lb = _heal_truncation(la, lb), _heal_truncation(lb, la)
    ta, tb = set(la), set(lb)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) > 0.6


_FORM_TAIL = re.compile(r"(\s+(gmbh|ag|se|kg|mbh|co|ug|inc|ltd|llc|bv|nv|plc|sa|a\.?\s?g\.?|&))+\s*$", re.I)


def named_in(company, text):
    """True when the company's name appears in text.

    Tested 29 Sep 2026 on 312 packs, each matched against every other sent job. Two ways it
    went wrong until fixed. "Innovation Group GmbH" had become "innovation" after the legal
    forms were stripped, and that word is in half the adverts, so only a trailing legal form
    is cut and "group" stays. And "STARK" matched the German word "stark", so a one-word name
    has to appear with its own capitalisation.
    """
    name = _FORM_TAIL.sub("", re.sub(r"\([^)]*\)", " ", ADMIN.sub(" ", company or ""))).strip()
    words = name.split()
    if not words:
        return False
    if len(words) == 1:
        w = words[0]
        return len(w) >= 4 and re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(w), text or "") is not None
    phrase = fold(name)
    return len(phrase) >= 6 and (" %s " % phrase) in (" %s " % fold(text or ""))


LINKEDIN_FOOTER = re.compile(r"referrals increase your chances of interviewing at[^.\n]*\.?|get notified about new [^.\n]*\.?", re.I)


def repeat_by_desc(title, seen, desc, head=600, company="", location=""):
    """A seen entry with the same title whose employer is named near the top of desc.

    28 Sep 2026, two shapes the company string cannot fix. About twelve XING rows a run
    arrive with the company field empty (Smartly, Phantasma Labs, KUKA, ai-coustics,
    xHeron were all sent before and came back as new). And LinkedIn sometimes names the
    posting account: "Mitsui Chemicals Group" for an ARRK Engineering advert, "Mecklenburgische
    Versicherungs-Gesellschaft" for a HUK-COBURG one. In every case the real employer is
    named in the opening of the description.

    Guards, from the review of 29 Sep 2026. Customers and tools are named in adverts too: "Our
    clients include FINN and Sixt" matched a sent FINN job, and "You develop LLM agents" matched
    the recruiter entry "develop (Developrec...)". So: when the row names its own company and
    that company appears in the description, the row is trusted and this fallback is skipped;
    recruiter entries are never matched this way; the employer must be named in the opening
    600 characters; and the two locations must agree.
    """
    if not desc:
        return None
    desc = LINKEDIN_FOOTER.sub(" ", desc or "")
    txt = desc[:head]
    # Only the opening counts: every LinkedIn description ends "Referrals increase your chances of
    # interviewing at <posting account>", so a whole-text check always found the row's own name
    # and this fallback never ran for Mitsui/ARRK or Mecklenburgische/HUK (review, 29 Sep 2026).
    if company and named_in(company, txt):
        return None
    for e in seen:
        ec = e.get("company", "")
        if re.search(r"recruiter|client not named|agency", ec, re.I):
            continue
        if not same_place(e.get("location", ""), location):
            continue
        if not named_in(ec, txt):
            continue
        if same_title(strip_company_affix(e.get("title", ""), e.get("company", "")),
                      strip_company_affix(title, e.get("company", ""))):
            return e
    return None


BA_REF = re.compile(r"arbeitsagentur\.de/jobsuche/jobdetail/([0-9A-Za-z-]+)")


# Query parameters that change nothing about which job a link points at. Briink's Personio link
# came back as ".../job/2777150?language=en" and no longer matched the sent link (29 Sep 2026).
# Only these are dropped: talent.com (?id=) and others carry the job in the query.
_NOISE_PARAM = re.compile(r"^(language|lang|locale|hl|utm_\w+|ref|refid|source|src|gh_src|lever-\w+|trk|trackingid|"
                          r"from|origin|mode|embed|referrer|campaign)$", re.I)


def norm_url(u):
    u = (u or "").strip()
    if "?" not in u:
        return u.rstrip("/")
    base, _, q = u.partition("?")
    keep = [kv for kv in q.split("&") if kv and not _NOISE_PARAM.match(kv.split("=", 1)[0])]
    return (base.rstrip("/") + ("?" + "&".join(keep) if keep else "")).rstrip("/")


def _links(e):
    """Every link a seen entry carries. state/seen.json used to keep one; write_pack stores `urls` since
    29 Sep 2026, because CHECK24's Bundesagentur copy came back as new while its employer link
    was the only one stored."""
    out = [e.get("url") or ""] + list(e.get("urls") or [])
    return {norm_url(u) for u in out if u}


def is_repeat(company, title, location, seen, url="", desc=""):
    """Return the matching seen entry, or None. Check this, not just the id.

    Pass desc when the row has one. It is only used after every company-based test failed.
    A title that names its employer with "@X" ("Product Engineer (Backend/AI) @Briink", posted
    by Merantix) is also checked with X as the company (review, 29 Sep 2026)."""
    m = _is_repeat(company, title, location, seen, url, desc)
    if m is None:
        at = re.search(r"@\s*([A-Za-z0-9][\w.\-]{2,})", title or "")
        if at and not same_company(at.group(1), company or ""):
            m = _is_repeat(at.group(1), title, location, seen, url, "")
    return m


def _is_repeat(company, title, location, seen, url="", desc=""):
    cid = canonical_id(company, title, location)
    u = norm_url(url)
    u_is_index = bool(u and _INDEX_URL.match(u))
    if u and u in _ambiguous_urls(seen):
        u = ""
    ref = BA_REF.search(u or "")
    # 2 Oct 2026: the job itself first, over every entry: the same id, the same link, the same BA
    # reference. Only then a job that merely looks alike. In one loop, an older look-alike came back
    # before the job's own entry: Quantum-Systems "Senior Robotics & Machine Learning Engineer" matched
    # "Senior Machine Learning Engineer" of 1 Aug, was taken for a second opening beside it, and was
    # sent on 29 Sep, again that evening, and twice on 2 Oct, each time under the same link.
    for e in seen:
        if e.get("id") == cid:
            return e
        links = _links(e)
        if u and u in links:
            return e
        if ref and any(ref.group(1) == (BA_REF.search(x) or [None, None])[1] for x in links):
            return e
    for e in seen:
        if not same_company(e.get("company", ""), company):
            continue
        ea = strip_board_tail(strip_company_affix(e.get("title", ""), e.get("company", "")), _links(e))
        eb = strip_board_tail(strip_company_affix(title, company), [url])
        if same_title(ea, eb):
            return e
        if desc and same_place(e.get("location", ""), location) and title_in_desc(ea, eb, desc):
            return e
        # Employers with no per-job urls: every opening is stored under the one careers
        # page, so the url branch above is deliberately disabled for them (see _INDEX_URL)
        # and the 0.75 title bar is the only guard left. It is too high when the *same*
        # role reaches the radar retitled by different sources. Sikia, 7 Sep 2026 evening:
        # "Founding Engineer - Applied AI Engineering & Full-Stack (d/f/m)" (sent 2 Sep)
        # vs "Founding Engineer (Applied AI / Backend Engineering)" (the company's own
        # page today) scores 0.625 and came back as new -- the third send of one job, and
        # the 6 Sep send was already the second. So for same company + same location +
        # both urls a careers index on the same host, drop the bar to 0.5. That still
        # clears the microagi trap the _INDEX_URL comment describes: its genuinely
        # different roles ("Depth Research Engineer" vs "SLAM Research Engineer") score
        # well under 0.5, while one role wearing two titles scores well over it.
        eu = norm_url(e.get("url") or "")
        if u_is_index and _INDEX_URL.match(eu) and _host(eu) == _host(url) \
           and same_place(e.get("location", ""), location) \
           and same_title_loose(ea, eb):
            return e
    return repeat_by_desc(title, seen, desc, company=company or "", location=location or "")


if __name__ == "__main__":
    import sys
    seen = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "state/seen.json"))
    dupes = 0
    for i, e in enumerate(seen):
        # Pass the url. Without it the careers-index branch added 7 Sep 2026 never fires,
        # and the audit stayed silent on the very duplicates it exists to find: Sikia's
        # one job sits in this file three times over 2, 6 and 7 September.
        m = is_repeat(e["company"], e["title"], e.get("location", ""), seen[:i],
                      e.get("url", ""))
        if m:
            dupes += 1
            print("DUPLICATE %s  %s | %s\n       of %s  %s | %s"
                  % (e["sent"], e["company"][:34], e["title"][:52],
                     m["sent"], m["company"][:34], m["title"][:52]))
    print("%d entries, %d duplicates" % (len(seen), dupes))
