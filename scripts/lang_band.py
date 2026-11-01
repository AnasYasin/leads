#!/usr/bin/env python3
"""German-language band for a posting, per instructions/PROFILE.md (8 Sep 2026).

    A     little or no German: not mentioned, a plus, von Vorteil, wünschenswert, English-only
    B     B1 or more German asked: B1, B2, gute/solide Deutschkenntnisse, Deutsch in Wort und Schrift
    drop  C1, C2, fließend, verhandlungssicher, muttersprachlich, sehr gute Deutschkenntnisse,
          fluent/business-level/native German

`band(text)` returns (band, quoted sentence). The sentence is the exact line from the posting
that decided it, so the email can show it and the candidate can judge it himself. This is a first pass;
the agent reads the whole posting and can overrule it, and must say so when it does.
"""
import re

DROP = re.compile(
    # C1/C2 only count when they sit next to the German word, "Englisch (C1+), Deutsch von
    # Vorteil" is an English requirement and must not drop the job.
    r"(deutsch|german)\w*[^.;,]{0,25}\b(c1|c2)\b|\b(c1|c2)\b[^.;,]{0,12}(deutsch|german)|"
    # "fließend" counts against German only when no English word sits between them:
    # "Gute Deutschkenntnisse (B2) und Englisch fließend" is a B2 job. "Deutsch und Englisch
    # fließend" is handled by the both-languages line below.
    r"(deutsch|german)\w*(?:(?!englisch|english)[^.;]){0,40}flie(ß|ss)end|flie(ß|ss)end\w*[^.;]{0,25}(deutsch|german)|"
    r"(deutsch|german) (und|and) (englisch|english)\w*[^.;]{0,15}(flie(ß|ss)end|fluent|verhandlungssicher)|"
    r"fluent\w* (in )?(both )?(english and )?german|"
    r"verhandlungssicher|muttersprach|native (german|speaker)|"
    # "Sehr gute Englischkenntnisse und Deutschkenntnisse" (BaehrBots, 29 Sep 2026) is a drop: the
    # "sehr gute" governs both nouns. Allow one intervening "<lang>kenntnisse und" before Deutsch.
    r"(?:sehr gute[ns]?|ausgezeichnete[ns]?|exzellente[ns]?)\s+(?:\w+kenntnisse\s+(?:und|sowie)\s+)?deutsch|"
    r"fluency in german|business[- ]level german|"
    r"professional (working )?proficiency in german|german at (a )?(native|c1|c2)|"
    r"deutsch(kenntnisse)? (auf )?(c1|c2)|perfekte[ns]? deutsch|deutsch als muttersprache|"
    r"german (is|are) (mandatory|required|a must)\b(?![^.]*\bplus)", re.I)
B = re.compile(
    r"\b(b1|b2)\b|gute[ns]? deutsch|solide[ns]? deutsch|deutsch in wort und schrift|"
    r"deutschkenntnisse (sind )?(erforderlich|vorausgesetzt|notwendig|zwingend)|"
    r"good (command of |knowledge of |level of )?german|intermediate german|"
    r"conversational german|working knowledge of german|"
    r"german (skills|language skills|knowledge) (are |is )?(required|necessary|needed)|"
    r"(sichere|fundierte) deutschkenntnisse", re.I)
PLUS = re.compile(
    r"deutsch\w* (sind |ist |wären? )?(von vorteil|ein plus|wünschenswert|nice to have|"
    r"vorteilhaft|hilfreich|kein muss|nicht erforderlich|not required|optional)|"
    r"german (is |are |would be )?(a plus|a bonus|nice to have|an advantage|of advantage|"
    r"beneficial|helpful|not required|not necessary|optional|welcome)|"
    r"english[- ]speaking (team|environment|company)|"
    r"(working|company|team) language is english|english is (our |the )?(working|company) language|"
    r"no german (required|needed|necessary)", re.I)
MENTION = re.compile(r"deutsch|german", re.I)


def _sentences(text):
    # Split on sentence ends, bullets and line breaks. A hyphen is not a split point: "Sehr
    # gute Deutsch- und Englischkenntnisse" is one sentence and the quote must carry all of it.
    return [s.strip() for s in re.split(r"(?<=[.!?\n•·])\s+|\n", text or "") if s.strip()]


def band(text):
    """(band, quoted sentence). "drop" and "decide" come from `german` below (2 Oct 2026); A and B are
    told apart as before. "decide" means the line is unclear and the agent must quote it and decide."""
    sents = _sentences(text)
    hits = [s for s in sents if MENTION.search(s)]
    if not hits:
        return "A", "no language line in the posting"
    verdict, lines = german(text)
    if verdict != "ok":
        return verdict, " || ".join(lines[:2])[:400]
    for s in hits:
        if PLUS.search(s):
            return "A", s[:240]
    for s in hits:
        if B.search(s):
            return "B", s[:240]
    # German is mentioned but with no level. A German-language advert with no English line
    # goes to B per instructions/PROFILE.md; an English advert that merely mentions Germany stays A.
    line = hits[0][:240]
    if re.search(r"\bdeutsch(kenntnisse|sprachig)?\b", line, re.I) and not re.search(r"englisch|english", text or "", re.I):
        return "B", line
    return "A", line


if __name__ == "__main__":
    import sys
    print(band(sys.stdin.read()))


def hard_drop(text):
    """The sentence that disqualifies the posting on German alone, or None. Since 2 Oct 2026 this is
    the "drop" verdict of `german` below: certain cases only. Unclear lines are `to_decide`."""
    verdict, lines = german(text)
    return lines[0] if verdict == "drop" else None


# ---------------------------------------------------------------------------------------------
# 2 Oct 2026: the German line, read clause by clause (docs/PROBLEMS.md group 3, the candidate's split).
#
# Three outcomes for a posting:
#   drop     certain. One sentence gives German a level he does not have, and nothing in that
#            sentence softens it or offers English in its place. Dropped unread.
#   decide   unclear. German sits next to a strong level word, but the sentence also softens it,
#            names other languages as alternatives, or the level cannot be tied to German. The row
#            stays, the lines are attached to it, and the agent must quote one and decide.
#   ok       no German line, a plus, or a level he has (B1, "gute", "sichere").
#
# The regex lists above tied a level to German by distance in characters, which is why "English
# (C1+)" killed a job and "Fluency in English and German required" did not. Here every language
# named in a sentence gets its own level: the adjective right before it ("fließende
# Deutschkenntnisse"), the level right after it ("Deutsch (C1)", "German - fluent"), or the level
# of the language it is joined to ("Deutsch und Englisch verhandlungssicher").
#
# the candidate's decisions of 2 Oct 2026: B2 is a drop. "Sichere Deutschkenntnisse" and "kommunizierst
# sicher auf Deutsch" stay Band B. A German advert that names no level stays Band B.
_DE = (r"(?:deutsch(?!land|e[nrsm]?\b|sprachig|sprechend|kurs)[\w]*|deutsche[rnm]?\s+sprach\w*"
       r"|deutsche[rnm]?(?=\s+(?:und|oder|sowie|&)\s+englische[rnm]?\s+sprach)"
       r"|german(?![yi])\b(?=\s*(?:$|[.,;:()/&]|[-–]\s|and\b|or\b|oder\b|und\b|is\b|are\b|at\b|as\b|on\b|to\b|skills?\b|language\b"
       r"|proficien\w*|knowledge\b|speakers?\b|level\b|fluen\w*|communication\b|native\b|required\b|mandatory\b"
       r"|would\b|will\b|both\b|written\b|spoken\b|a\s|[abc][12]\b|\(|helps?\b|plus\b|preferred\b|desir\w*|not\b|only\b"
       r"|from\b|with\b|for\b|min\b|minimum\b|\d)))")
_EN = r"(?:englisch\w*|english\b)"
_OTHER = (r"(?:franz(?:ö|oe)sisch\w*|french\b|italienisch\w*|italian\b|spanisch\w*|spanish\b|niederl(?:ä|ae)ndisch\w*|dutch\b"
          r"|portugiesisch\w*|portuguese\b|polnisch\w*|polish\b|russisch\w*|russian\b|t(?:ü|ue)rkisch\w*|turkish\b"
          r"|arabisch\w*|arabic\b|chinesisch\w*|chinese\b|mandarin\b|japanisch\w*|japanese\b|local language|landessprache)")
_LANG = re.compile(r"(?P<de>%s)|(?P<en>%s)|(?P<other>%s)" % (_DE, _EN, _OTHER), re.I)
# A level he does not have. B2 since 2 Oct 2026.
_STRONG = re.compile(
    r"\b(?:c1|c2|b2)\b|fluen(?:t|cy|tly)|flie(?:ß|ss)end\w*|fl(?:ü|ue)ssig\w*|verhandlungssicher\w*|near[- ]native|native"
    r"|muttersprach\w*|mother tongue|business[- ](?:fluent|level|proficien\w+)|gesch(?:ä|ae)ftssicher\w*"
    r"|(?:full |high )?professional (?:working )?proficiency|professional level|professionelle[mnrs]? niveau"
    r"|sehr gut\w*|very good|excellent\w*|exzellent\w*|sprachgewandt\w*"
    r"|ausgezeichnet\w*|hervorragend\w*|perfekt\w*|perfect\w*|impeccable|einwandfrei\w*|tadellos\w*|stilsicher\w*"
    r"|outstanding", re.I)
_CEFR = re.compile(r"c1|c2|b2", re.I)
_RANK = {"weak": 0, "medium": 1, "strong": 2}
# Strong-sounding, but not a level. With German and nothing softer, the agent decides.
_MEDIUM = re.compile(r"\bstrong\b|\bstark\w*|kommunikationsstark\w*|advanced|fortgeschritten\w*|proficien\w+", re.I)
# A level he has. It also stops German from borrowing the level of the language next to it:
# "gute Deutschkenntnisse und sehr gute Englischkenntnisse".
_WEAK = re.compile(r"\bgute?[nrsm]?\b|\bgood\b|solide\w*|\bsolid\b|sicher\w*|grundkenntnisse|grundlegend\w*|\bbasic\b|conversational"
                   r"|\b(?:a1|a2|b1)\b", re.I)
# A German working language is in the Drop band of instructions/PROFILE.md, but the wording varies. He decides.
_WORK_LANG = re.compile(r"(?:working|company|project|team|office) language (?:is|will be) german|german is (?:the|our) (?:\w+ )?language"
                        r"|(?:arbeits|unternehmens|projekt|team)sprache (?:ist |: ?)?deutsch|deutsch (?:ist|als) (?:unsere )?(?:arbeits|unternehmens)sprache", re.I)
# "mind. C1", "z. B.": a full stop that does not end the sentence.
_ABBR = re.compile(r"\b(mind|min|max|ca|bzw|inkl|zzgl|evtl|ggf|usw|etc|approx|incl|vgl|nr|z\.\s?b|u\.\s?a|d\.\s?h|e\.\s?g|i\.\s?e|o\.\s?ä)\.\s+", re.I)
# Anything that makes a German line less than a requirement. "Runden dein Profil ab" is not in
# this list: the candidate decided on 2 Oct 2026 that "Sehr gute Deutschkenntnisse runden dein Profil ab" is a drop.
_SOFTEN = re.compile(
    r"vorteil|\bplus\b|w(?:ü|ue)nschenswert|erw(?:ü|ue)nscht|nice[- ]to[- ]have|advantage|bonus|beneficial|helpful|hilfreich"
    r"|welcome|willkommen|prefer\w+|bevorzugt|desir(?:able|ed)|\bideal\w*|optional|kein muss|not (?:required|necessary|needed|mandatory|a must|a requirement)"
    r"|nicht (?:erforderlich|zwingend|notwendig|n(?:ö|oe)tig)|keine voraussetzung|willing\w* to learn|lernen\b|\blearn(?:ing)?\b"
    r"|\b(?:a1|a2|b1)\b|grundkenntnisse|basic|ausreichend|sufficient|\bhelps?\b|appreciated|\basset\b|gern gesehen"
    r"|any level|is fine|reicht|or equivalent|oder vergleichbar|depending on|je nach|if applicable|where applicable"
    r"|working knowledge|conversational|grundlegend\w*", re.I)
# Words that may stand between a level and the language it describes. Checked word by word, so a
# long gap fails at once (a regex with nested repeats took seconds on a flattened posting).
_PRE_WORDS = set("""in auf of im der die the both command knowledge skill skills level niveau kenntnisse proficiency
    written spoken and und verbal oral communication wort schrift sprachkenntnisse language sowohl or als auch
    mündlich mündliche mündlichen muendlich schriftlich schriftliche schriftlichen kommunikation ausdrucksweise
    sprachgewandtheit beherrschung sprach presentation präsentation fluency business""".split())
_PRE_STEMS = ("kommunikationsf", "ausdrucksf", "präsentations", "praesentations")
_POST_WORDS = set("""kenntnisse sprachkenntnisse in wort und schrift auf at is are sind ist skill skills language level
    niveau mindestens mind min minimum least a an dem einem proficiency required erforderlich written spoken sprache
    of the or als auch sowie from for jeweils each both beides sicher sicherem sicheren gutem guten""".split())


def _gap_ok(gap, words, stems=(), punct="-–+", limit=8, short=0):
    """True when the text between a level and a language is only filler: the listed words, words of
    up to `short` letters, and the listed punctuation."""
    if len(gap) > 90:
        return False
    toks = re.findall(r"\w+|[^\w\s]", gap.lower())
    if len(toks) > limit + 6:
        return False
    n = 0
    for t in toks:
        if not (t[0].isalnum() or t[0] == "_"):
            if t not in punct:
                return False
            continue
        n += 1
        if not (t in words or len(t) <= short or t.startswith(stems)):
            return False
    return n <= limit


class _Gap:
    def __init__(self, words, stems=(), punct="-–+", limit=8, short=0):
        self.args = (words, stems, punct, limit, short)

    def match(self, gap):
        return _gap_ok(gap, *self.args)


_PRE_GAP = _Gap(_PRE_WORDS, _PRE_STEMS, "-–+/()", 6)
_POST_GAP = _Gap(_POST_WORDS, (), "-–:(),.", 8, short=3)
# Between a German word and a softener further along a list of languages:
# "Proficiency in German, Italian, French or Portuguese is a plus".
_LIST_FILL = set("or oder and und is are a an ein eine sind ist wäre waere would be skills kenntnisse sowie as well".split())
_JOIN = re.compile(r"^[\s\-–]*(?:kenntnisse\s*)?(?:,|und|and|sowie|&|/|\+|as well as|wie auch|plus)\s*(?:auch\s+|in\s+|both\s+)?[\s\-–]*$", re.I)
_OR = re.compile(r"^[\s\-–]*(?:kenntnisse\s*)?(?:,\s*)?(?:oder|or|bzw\.?|/)\s*[\s\-–]*$", re.I)
# A short line above a list that makes the list optional.
_SOFT_HEAD = re.compile(r"^\W*(?:nice[- ]to[- ]haves?|ein plus|von vorteil|bonus\w*|w(?:ü|ue)nschenswert|optional|plus(?:punkte)?|pluspoints?"
                        r"|what would be a plus|it(?:'|’)s a plus if|not required but|das w(?:ä|ae)re toll|good to have|preferred(?: qualifications)?"
                        r"|was uns (?:noch )?begeistert|extra credit|bonus points?|ideal(?:erweise|ly)(?:\s+\w+){0,3}|toll w(?:ä|ae)re"
                        # 3 Oct 2026: a qualified heading, "Wünschenswerte Qualifikationen:" (a university post
                        # was dropped on a C1 line listed under it), "Preferred skills".
                        r"|(?:w(?:ü|ue)nschenswerte?|optionale?|preferred|desired|desirable|additional|bonus|nice[- ]to[- ]have)"
                        r"\s+(?:qualifikationen|qualifications|kenntnisse|skills|requirements|experience|erfahrungen?))\W*$", re.I)


# A short line above a list that makes the list a set of requirements. Only under one of these, or in
# running text with no list around it, can a German line drop a job without the agent (3 Oct 2026).
_HARD_HEAD = re.compile(r"^\W*(?:(?:your |dein |ihr |the |our |key |required |minimum |basic |core |erforderliche |notwendige |zwingende )?(?:profile?|profil|requirements?"
                        r"|qualifications?|qualifikation(?:en)?|anforderungen|anforderungsprofil|voraussetzungen|skills(?: and experience)?"
                        r"|must[- ]haves?|kenntnisse(?: und erfahrungen)?|erfahrungen?|experience|background)"
                        r"|what (?:you(?:'|’)ll|you will|you) (?:bring|need|have)|what we(?:'|’)re looking for|what we are looking for"
                        r"|what we expect|who you are|about you|you have|you bring|you should have|we expect|we(?:'|’)re looking for"
                        r"|das bringst du mit|was du mitbringst|was sie mitbringen|das bringen sie mit|das zeichnet dich aus"
                        r"|das zeichnet sie aus|was wir erwarten|wir erwarten|was wir uns w(?:ü|ue)nschen|deine skills|ihre skills"
                        r"|du bringst mit|sie bringen mit|du hast|sie haben|mitbringen solltest du)\W*$", re.I)


def _lines(text):
    """(line, the heading the line sits under) for every line of the text: "soft" under a "nice to
    have" heading, "hard" under a requirements heading, "unknown" under any other heading, None in
    running text. A heading line itself counts as running text."""
    mode, out = None, []
    for raw in (text or "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        item = line[:1] in "•·-*–" and len(line) > 2
        here = mode if item else None
        if not item and len(line) <= 60:
            # A new heading sets the tone for its list. Non-breaking spaces count as spaces.
            head = re.sub(r"\s+", " ", line)
            mode = "soft" if _SOFT_HEAD.match(head) else "hard" if _HARD_HEAD.match(head) else "unknown"
        elif not item:
            mode = None                               # a paragraph ends the list
        out.append((line.lstrip("•·-*– ").strip(), here))
    return out


def _clauses(line):
    line = _ABBR.sub(lambda m: m.group(0).rstrip() + "\u00a0", line)
    # A list that arrived on one line ("... wünschenswert - Sichere Anwendung von Git - Verhandlungssichere
    # Deutsch- und Englischkenntnisse", Akkodis and Orizon) is split at its item marks, so a softener in
    # one item does not soften the next. One " - " alone is left: "German - Fluent (C1)".
    rx = r"(?<=[.!?])[ \t]+|\s*[;•·]\s*"
    if line.count(" * ") >= 2:
        rx += r"|\s\*\s"
    if line.count(" - ") >= 3:
        rx += r"|\s-\s"
    return [s.replace("\u00a0", " ").strip() for s in re.split(rx, line) if s.strip()]


def _levels(s):
    """Per language named in the sentence: [kind, start, end, level word or None, grade]. The grade
    is "strong", "medium" or "weak", from the level word that belongs to that language."""
    langs = [(m.lastgroup, m.start(), m.end()) for m in _LANG.finditer(s)]
    marks = sorted([(m.start(), m.end(), "strong") for m in _STRONG.finditer(s)]
                   + [(m.start(), m.end(), "medium") for m in _MEDIUM.finditer(s)]
                   + [(m.start(), m.end(), "weak") for m in _WEAK.finditer(s)])
    # A weak word inside a strong one ("sehr gute") is part of it.
    marks = [m for i, m in enumerate(marks)
             if not any(o is not m and o[2] == "strong" and o[0] <= m[0] and m[1] <= o[1] for o in marks[max(0, i - 3):i + 4])]
    strong = [(x, y) for x, y, _ in marks]
    grade = {(x, y): g for x, y, g in marks}
    own = []
    for i, (kind, a, b) in enumerate(langs):
        prev_end = langs[i - 1][2] if i else 0
        next_start = langs[i + 1][1] if i + 1 < len(langs) else len(s)
        lvl = None
        for x, y in strong:
            # The adjective right before the language: "fließende Deutschkenntnisse", "fluent in German".
            # Of several, the strongest counts: "native or near-native proficiency in German".
            if prev_end <= x and y <= a and _PRE_GAP.match(s[y:a]) \
                    and (lvl is None or _RANK[grade[(x, y)]] >= _RANK[lvl[1]]):
                lvl = (s[x:y], grade[(x, y)])
            # A strong word glued to the language word itself: "C1-Deutschkenntnisse".
            if a <= x and y <= b:
                lvl = (s[x:y], grade[(x, y)])
        # A stated CEFR level right after the language outranks the adjective before it:
        # "Gute Deutschkenntnisse (C1-Niveau)".
        if lvl is None or lvl[1] != "strong":
            for x, y in strong:
                if b <= x and x - b <= 40 and _CEFR.fullmatch(s[x:y]) and _POST_GAP.match(s[b:x]) and x < next_start:
                    lvl = (s[x:y], grade[(x, y)])
                    break
        if lvl is None:
            for x, y in strong:
                # The level right after it: "Deutsch (C1)", "German - fluent", "Deutsch ist verhandlungssicher".
                if b <= x and y <= next_start + (0 if i + 1 < len(langs) else 1) and x - b <= 60 and _POST_GAP.match(s[b:x]):
                    lvl = (s[x:y], grade[(x, y)])
                    break
        own.append([kind, a, b, lvl[0] if lvl else None, lvl[1] if lvl else None])
    # "(beide Sprachen min. C1)": one level for every language in the sentence.
    both = re.search(r"beide[nr]? sprachen|both languages|in beiden sprachen", s, re.I)
    top = next(((s[x:y], g) for x, y, g in marks if g == "strong"), None)
    if both and top:
        for o in own:
            o[3:] = list(top)
    # Joined languages share a level: "Deutsch und Englisch verhandlungssicher", "fluent in English and German".
    # A language with its own softener borrows nothing: "fluent English, German is a plus".
    lone = [bool(_SOFTEN.search(s[o[2]:min(len(s), o[2] + 40, langs[i + 1][1] if i + 1 < len(langs) else len(s))]))
            for i, o in enumerate(own)]
    for _ in range(2):
        for i in range(len(own) - 1):
            if _JOIN.match(s[own[i][2]:own[i + 1][1]]) and not lone[i] and not lone[i + 1]:
                if own[i][3] and not own[i + 1][3]:
                    own[i + 1][3:] = own[i][3:]
                elif own[i + 1][3] and not own[i][3]:
                    own[i][3:] = own[i + 1][3:]
    return own


def _sentence(s, soft_head=False):
    """drop, decide, plus or None for one sentence."""
    lv = _levels(s)
    de = [x for x in lv if x[0] == "de"]
    if not de:
        return None
    # A softener counts when it stands near the German word, or the sentence has no comma to split it:
    # "Fluent German and English, AWS experience is a plus" still demands German.
    soft = soft_head
    pos = 0
    for seg in s.split(","):
        a, b = pos, pos + len(seg)
        pos = b + 1
        # A softener in a short segment of its own counts only when that segment is about a level:
        # ", bevorzugt C1", ", B2 ist ausreichend". Not ", idealerweise in einem Beratungsunternehmen".
        if _SOFTEN.search(seg) and (any(a <= x[1] < b for x in de) or (
                len(seg.split()) <= 4 and (_STRONG.search(seg) or re.search(r"\b[abc][12]\b", seg, re.I)))):
            soft = True
    for m in _SOFTEN.finditer(s):
        for x in de:
            if x[2] <= m.start():
                between = re.findall(r"\w+", _LANG.sub(" ", s[x[2]:m.start()]).lower())
                if len(between) <= 8 and all(w in _LIST_FILL for w in between):
                    soft = True
    # "German or English": English will do. "German, Italian or French": one of them must be his.
    alt_en = alt_other = False
    for i in range(len(lv) - 1):
        if _OR.match(s[lv[i][2]:lv[i + 1][1]]) and "de" in (lv[i][0], lv[i + 1][0]):
            other = lv[i + 1][0] if lv[i][0] == "de" else lv[i][0]
            alt_en |= other == "en"
            alt_other |= other == "other"
    if not alt_other and any(x[0] == "other" for x in lv) and re.search(r"\b(?:oder|or)\b", s, re.I):
        alt_other = True
    grades = {x[4] for x in de}
    if "strong" in grades:
        if alt_en:
            return "plus"
        return "decide" if (soft or alt_other) else "drop"
    if _WORK_LANG.search(s) and not soft:
        return "decide"
    if soft or alt_en:
        return "plus"
    if "medium" in grades:
        return "decide"
    if "weak" in grades:
        return None
    # A strong word in the sentence that belongs to no language named in it, with German named too:
    # "Sichere Kommunikation in Deutsch und Englisch (beide Sprachen min. C1)".
    tied = {x[3] for x in lv if x[3]}
    if any(m.group(0) not in tied for m in _STRONG.finditer(s)):
        return "decide"
    return None


def _windows(clauses):
    """A flattened posting can be one "sentence" of many thousand characters. Such a clause is read
    as a window of text around each German word, which is all the rule looks at anyway."""
    for s in clauses:
        if len(s) <= 1200:
            yield s
            continue
        last = -1
        for m in MENTION.finditer(s):
            if m.start() < last:
                continue
            last = m.end() + 300
            yield s[max(0, m.start() - 300):last]


def _quote(s):
    """The sentence as it will be quoted. Of a long one, the part around the German word."""
    if len(s) <= 240:
        return s
    m = next((x for x in _levels(s) if x[0] == "de" and x[4] == "strong"), None) or next(
        (x for x in _levels(s) if x[0] == "de"), None)
    if not m:
        return s[:240]
    return ("..." + s[max(0, m[1] - 110):m[2] + 120] + "...").strip()


def german(text):
    """(verdict, lines) for a posting: "drop", "decide" or "ok", and the sentences that decided it."""
    drop, decide, plus = [], [], []
    for line, head in _lines(text):
        for s in _windows(_clauses(line)):
            if not MENTION.search(s):
                continue
            v = _sentence(s, head == "soft")
            # 3 Oct 2026 (the candidate): drop only on a confirmed requirement. A strong German line in a list
            # under a heading the code does not know ("Extras:", or "Nice-to-Haves:" before the plural
            # was added, which rejected Deepslate at fit 8) goes to the agent to decide.
            if v == "drop" and head == "unknown":
                v = "decide"
            if v == "drop":
                drop.append(_quote(s))
            elif v == "decide":
                decide.append(_quote(s))
            elif v == "plus" and PLUS.search(s):
                plus.append(_quote(s))
    if drop and not plus:
        return "drop", drop
    # A posting that demands German in one place and calls it a plus in another contradicts itself.
    if drop or decide:
        return "decide", list(dict.fromkeys(drop + decide + (plus if drop else [])))[:4]
    return "ok", plus[:1]


def to_decide(text):
    """The German lines the agent must quote and decide on, or []. See `german`."""
    v, lines = german(text)
    return lines if v == "decide" else []
