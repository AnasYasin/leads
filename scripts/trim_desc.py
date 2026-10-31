#!/usr/bin/env python3
"""Remove perk sentences and diversity boilerplate from a job description.

Added 29 Sep 2026 at the candidate's request, to cut what the run has to read. Responsibilities and the
company description must never be touched (the candidate, same day).

How it works: the description is split into sentences and bullet items. A piece is removed when
it names a perk (vacation days, JobRad, gym, canteen, discounts, pension, team events...) and
says nothing about the work, the company, pay, language, location or visa. Diversity and
equal-opportunity sentences go the same way. Nothing else is removed, and no section is cut.

Why sentences and not sections. A section cut (from "What we offer" to the next heading) was
built and measured first on 442 descriptions. Adverts arrive flattened to one line, so the end
of a section is a guess, and the cut removed real lines: ClickHouse "What you'll do: Own and
evolve ...", Wolt "You will work on recommendation problems ...", part of HUK-COBURG's task list
and one of Omnora's tasks. It saved 8.5% of the text. This version saves 3.7%, changes no salary,
German band or hard German drop on any of the 442, and removed no task or company sentence.

    python3 scripts/trim_desc.py < description.txt      print the trimmed text and what was cut
"""
import re
import sys

PERK = re.compile(
    r"urlaub|vacation|holiday|days? off|paid leave|sabbatical|workation|jobrad|job ?bike|bike leasing|wellpass|"
    r"hansefit|urban sports|egym|\bgym\b|fitness|kantine|cafeteria|canteen|lunch|mittagessen|obst|fruit|snacks|"
    r"drinks|getränke|kaffee|coffee|barista|team ?events?|sommerfest|weihnachtsfeier|offsites?|\bbav\b|"
    r"betriebliche altersvorsorge|pension|altersvorsorge|corporate benefits|rabatt|discounts?|deutschlandticket|"
    r"jobticket|public transport|zuschuss|subsid|\bkita\b|childcare|kinderbetreuung|dog[- ]friendly|parking|parkpl|"
    r"weiterbildungsbudget|learning budget|l&d budget|gleitzeit|vertrauensarbeitszeit|wellbeing|well-being|"
    r"mental health|health insurance|betriebsarzt|massage", re.I)
# Never removed: pay, language, location, relocation, visa. These sit in benefits lists and do
# decide a job (salary.py, lang_band.py, the location rule). Office days are not kept: the candidate takes
# any location in Germany and any number of office days.
KEEP = re.compile(
    r"€|\beur\b|\beuro\b|\$|salary|gehalt|verg[üu]tung|compensation|\bcomp\b|equity|base salary|variable|brutto|tv-?l|tv[öo]e?d|"
    r"deutsch|german|english|englisch|sprach|language|"
    r"fully remote|100% remote|remote from|standort|location|relocat|umzug|visa|visum|work permit|arbeitserlaubnis",
    re.I)
# Never removed either: anything about the work or the company.
WORK = re.compile(
    r"\b(you will|you'll|you are responsible|your responsibilit|what you(?:'|’)ll do|du entwickelst|du baust|du arbeitest|"
    r"du bist verantwortlich|du gestaltest|sie entwickeln|sie verantworten|ihre aufgaben|deine aufgaben|develop|design|"
    r"implement|build|train|deploy|model|pipeline|data|daten|research|forschung|product|produkt|customer|kunde|client|"
    r"our mission|we are a|founded|gegründet|employees|mitarbeiter|headquarter|hauptsitz|entwickl|konzip|führe |aufgabe)", re.I)
# Only real equal-opportunity phrasings. Bare "diversity", "diverse" and "inclusive" cut work lines
# on real adverts (review, 29 Sep 2026): Mistral "adaptable to a diversity of clients ... Partner with
# researchers", Clera "Develop metrics to quantify synthetic task diversity", n8n "grown into a diverse
# team of over 260" (the headcount the salary ask needs).
DIVERSITY = re.compile(
    r"[^.!?\n]*(?:equal opportunit|regardless of (?:race|gender|age|religion|sex|origin|background)|"
    r"we (?:welcome|encourage) applications from|committed to (?:diversity|inclusion|equal)|"
    r"chancengleichheit|diskriminierungsfrei|unabhängig von (?:geschlecht|herkunft|alter|religion|nationaler)|"
    r"schwerbehindert|\bagg\b)[^.!?\n]*[.!?]?", re.I)
# A diversity sentence that talks about the work is never removed.
WORK_VERBS = re.compile(
    r"\b(develop|design|implement|build|train|deploy|model|pipeline|metric|research|partner|client|customer|"
    r"entwickl|konzip|you will|du wirst|team of|mitarbeiter(?:innen)? (?:in|an)|employees in)\w*", re.I)


# Flattened adverts can run hundreds of characters without a full stop, so one "sentence" may be a
# whole section. A piece that long is never removed (review, 29 Sep 2026: Peec AI's "What We Offer
# Transparent comp with a 50/50 base ..." went with an equal-opportunity line).
MAX_PIECE = 300


def _pieces(s):
    # Not on " - ": that split "65.000 - 90.000 EUR" in half (Enjins). Not after an abbreviation:
    # "Zielgehalt bis ca. 140.000 EUR" split after "ca." lost the band (workidentity).
    s = re.sub(r"\b(ca|bzw|inkl|zzgl|evtl|z\.\s?b|u\.\s?a|max|min|approx|incl|etc)\.\s+",
               lambda m: m.group(0).replace(" ", " "), s, flags=re.I)
    return [p.replace(" ", " ") for p in re.split(r"(?<=[.!?])\s+|\s+[•·]\s*|\n+|\s+\*\s+", s) if p.strip()]


def trim(text):
    """(trimmed text, number of characters removed). Never raises."""
    t = text or ""
    if not t:
        return "", 0
    try:
        res = t
        for p in _pieces(t):
            if len(p) > MAX_PIECE or KEEP.search(p):
                continue
            if PERK.search(p) and not WORK.search(p):
                res = res.replace(p, " ", 1)
            # Diversity pieces need only the work-verb guard: "We are an equal opportunity employer"
            # would otherwise pass the company guard on "we are a".
            elif DIVERSITY.search(p) and not WORK_VERBS.search(p):
                res = res.replace(p, " ", 1)
        # 2 Oct 2026: descriptions keep their lines now (scripts/textclean.py), one list item per
        # line. A removed perk item must take its bullet and its line with it.
        res = re.sub(r"(?m)^[ \t]*[•·]?[ \t]*$\n?", lambda m: "\n" if m.group(0) == "\n" else "", res)
        res = re.sub(r"[ \t]{2,}", " ", res)
        res = re.sub(r"(?m)^[ \t]+|[ \t]+$", "", res)
        res = re.sub(r"\n{3,}", "\n\n", res).strip()
        return res, max(0, len(t) - len(res))
    except Exception:
        return t, 0


if __name__ == "__main__":
    src = sys.stdin.read()
    new, cut = trim(src)
    print(new)
    print("\n-- %d of %d characters cut (%.0f%%)" % (cut, len(src), 100.0 * cut / max(1, len(src))), file=sys.stderr)
