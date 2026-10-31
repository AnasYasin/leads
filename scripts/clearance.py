#!/usr/bin/env python3
"""Nationality and security-clearance lines in a posting (docs/PROBLEMS.md 3.6, 2 Oct 2026).

The candidate this was written for is a non-EU national working in Germany. Decided 2 Oct 2026:

    drop   a nationality or citizenship requirement, always ("Must be a citizen of a NATO member
           state", "Nur Bewerber aus NATO und EU Mitglieds-Staaten"), and a firm clearance requirement
           ("eligibility for a security clearance is required", "Bereitschaft zur Ü2
           Sicherheitsüberprüfung"). Dropped unread, like a certain German requirement.
    flag   a conditional clearance line ("may need to be eligible for security clearance", "where
           required, obtain the relevant security clearance"). The job stays, and the sentence is put
           into its Gaps line by the code, so he sees it and decides.
    ok     everything else.

Three such jobs reached him between 30 Sep and 2 Oct: Autonomous Teaming twice ("Nationality of a NATO
member nation or close ally is required") and SAP ("may need to be eligible for security clearance
under German law"). The check before this one was a single regex over the reason an agent wrote, and
on the posting itself it ran only at the very end.

Most sentences that name a nationality are not requirements. Of 1,489 postings that used one of
these words on 2 Oct, the six most frequent sentences were equal-opportunity statements and team
descriptions ("regardless of ... citizenship", "60+ nationalities"), and "NATO" is mostly a customer
("NATO Allies"). Those are recognised first and never count.

    python3 scripts/clearance.py < posting.txt
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lang_band import _lines  # noqa: E402  (line by line, with "nice to have" headings)

NAT = re.compile(
    r"citizenship|\bcitizens?\b|\bnationalit(?:y|ät)\b|staatsangeh\w+|staatsb(?:ü|ue)rger\w*"
    r"|(?:applicants?|candidates?|bewerber\w*)\s+(?:from|aus)\s+(?:(?:nato|eu)\b[\w\s-]{0,8}){1,2}"
    r"|\bu\.?s\.? persons?\b|lawful permanent residents?|green card", re.I)
CLR = re.compile(
    # "clearance" alone is not enough: "customs clearance", "clear technical debt".
    r"security clearances?|(?:secret|ts/sci|\bsci\b|government|vetting|nato|national)\b[^.]{0,30}\bclearances?|clearable"
    r"|sicherheits(?:ü|ue)berpr\w+|\b(?:ü|ue)[123]\b|\bs(?:ü|ue)g\b|ts/sci|top secret"
    r"|geheimschutz\w*|verschlusssache\w*|security check\b|\bsc clearance|sicherheitsfreigabe\w*", re.I)
# A sentence about fairness, the team or the customers. It names a nationality and demands none.
NOT_A_RULE = re.compile(
    r"regardless|irrespective|unabh(?:ä|ae)ngig|without regard|equal (?:employment )?opportunit|discriminat|diskriminier"
    r"|on the basis of|based on race|auf basis von|prioriti[sz]e|welcomes? (?:people|all|applications)|willkommen"
    r"|nationalities|nationalit(?:ä|ae)ten|\bdivers|for visa|visa processing|visa sponsorship|serve citizens|for citizens"
    r"|of citizens|and citizens|citizen(?:s)? (?:services|experience|engagement|developers?|administration)|citizen science"
    r"|global citizen|non-eu citizens|impacts? citizens|first[- ]class citizen|corporate citizen|digital citizen|citizen developer"
    # the words a nationality stands between in an equal-opportunity list
    r"|religion|geschlecht|\bgender\b|herkunft|sexuell|sexual orientation|ethnic|ethnisch|\balter\b|\bage\b", re.I)
NO_NEED = re.compile(
    r"\bno (?:security )?clearance (?:is )?(?:required|needed|necessary)|clearance (?:is )?not (?:required|needed|necessary)"
    r"|(?:citizenship|nationality|clearance)\w*[^.]{0,25}(?:not required|not needed|nicht erforderlich|not a requirement)"
    r"|keine sicherheits(?:ü|ue)berpr", re.I)
FIRM = re.compile(
    r"requir|\bmust\b|mandatory|need(?:s|ed)? to|\bonly\b|\bnur\b|zwingend|erforderlich|voraussetz|vorausgesetzt|notwendig"
    r"|will not be considered|akzeptiert|\beligib|\bhold\b|holding|obtain|bereitschaft|einverst(?:ä|ae)ndnis|necessary"
    r"|\bactive\b|\bcurrent\b|aktive|g(?:ü|ue)ltige|subject to|unterliegt|essential|prerequisite|pflicht"
    r"|at least|mindestens|willing\w*|\bbereit\b|looking for|due to the nature|aufgrund der art|meet the (?:conditions|requirements)", re.I)
# Words that make a requirement firm even with a "preferred" further along the sentence.
STRONG = re.compile(r"\bmust\b|mandatory|zwingend|(?:is|are) required|required:|\brequires?\b|erforderlich|voraussetz"
                    r"|\bonly\b|\bnur\b", re.I)
MAYBE = re.compile(
    r"\bmay\b|\bmight\b|\bcould\b|can be required|where (?:required|necessary|applicable)|if (?:required|necessary|applicable)"
    r"|as (?:required|needed)|when required|depending|je nach|gegebenenfalls|\bggf\b|im einzelfall|m(?:ö|oe)glich\w*"
    r"|k(?:ö|oe)nnen\b|bei bedarf|potentially|some (?:roles|projects|positions)|for certain|is a plus|an advantage|advantage"
    r"|von vorteil|nice to have|encouraged|preferred|desirable|w(?:ü|ue)nschenswert|ideally|idealerweise|\bbonus\b", re.I)
# What will do in place of the citizenship. A work permit he has. A permanent residence he may not.
PERMIT_ALT = re.compile(r"\bor\b[^.]{0,40}(?:work permit|right to work|work authori[sz]ation|eligible to work|arbeitserlaubnis|visa)"
                        r"|\boder\b[^.]{0,40}(?:arbeitserlaubnis|aufenthaltstitel)", re.I)
RESIDENT_ALT = re.compile(r"\bor\b[^.]{0,40}(?:permanent residen|resident)|\boder\b[^.]{0,40}niederlassungserlaubnis", re.I)
# A full stop that does not end the sentence: "U.S. citizenship", "§ 13 para. 1 no. 17 SÜG".
ABBR = re.compile(r"\b(u\.s|u\.k|e\.g|i\.e|para|no|nr|abs|art|mind|min|bzw|inkl|ca|z\.\s?b|d\.\s?h|ggf|vgl|etc)\.\s+", re.I)


def _sentences(line):
    line = ABBR.sub(lambda m: m.group(0).rstrip() + " ", line)
    return [s.replace(" ", " ").strip() for s in re.split(r"(?<=[.!?])[ \t]+|\s*[;•·]\s*", line) if s.strip()]


def _one(s, soft_head=False):
    """drop, flag or None for one sentence."""
    nat, clr = NAT.search(s), CLR.search(s)
    if not nat and not clr:
        return None
    if NO_NEED.search(s):
        return None
    if nat and not NOT_A_RULE.search(s):
        if PERMIT_ALT.search(s):
            return None
        if RESIDENT_ALT.search(s) or soft_head:
            return "flag"
        # "Citizens" in the plural is about people in general unless the sentence demands something.
        if re.fullmatch(r"citizens", nat.group(0), re.I) and not FIRM.search(s):
            return None
        # A citizenship named in a requirement, or standing alone as one ("NATO Citizenship:", "US Citizen").
        if FIRM.search(s) or len(s.split()) <= 5:
            return "flag" if MAYBE.search(s) and not STRONG.search(s) else "drop"
        return "flag"
    if clr:
        if NOT_A_RULE.search(s) and not FIRM.search(s):
            return None
        # "May" softens the clearance when it stands before it or right after it. Further along it is
        # about something else: "MUST be eligible for UK Security Clearance and be able to travel when required".
        spans = [(m.start(), m.end()) for m in CLR.finditer(s)]
        before = any(m.start() < spans[-1][0] for m in MAYBE.finditer(s))
        after = any(spans[-1][1] <= m.start() < spans[-1][1] + 40 for m in MAYBE.finditer(s))
        if soft_head or before or (after and not STRONG.search(s)):
            return "flag"
        if FIRM.search(s):
            # A bare heading such as "Security Clearance Requirements" says nothing yet.
            return "flag" if len(s.split()) <= 3 and re.search(r"requirements?\s*:?$", s, re.I) else "drop"
        return "flag"
    return None


def check(text):
    """(verdict, sentences): "drop", "flag" or "ok", and the sentences that decided it."""
    drop, flag = [], []
    for line, soft_head in _lines(text):
        for s in _sentences(line):
            v = _one(s, soft_head)
            if v == "drop":
                drop.append(s[:300])
            elif v == "flag":
                flag.append(s[:300])
    if drop:
        return "drop", list(dict.fromkeys(drop))[:3]
    if flag:
        return "flag", list(dict.fromkeys(flag))[:3]
    return "ok", []


def gap_text(lines):
    """The sentence as it goes into a job's Gaps line."""
    return "Clearance or nationality line, check before you apply: '%s'" % lines[0] if lines else ""


if __name__ == "__main__":
    print(check(sys.stdin.read()))
