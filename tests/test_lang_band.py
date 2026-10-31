import pytest

from lang_band import band, german, hard_drop, to_decide


@pytest.mark.parametrize("text", [
    "Sprachkenntnisse: Sehr gute Deutschkenntnisse (C1-Level).",
    "Dein Deutsch und Englisch ist verhandlungssicher.",
    "Du kommunizierst fließend auf Deutsch und verhandlungssicher auf Englisch .",
    "Fließende Deutsch- sowie gute Englischkenntnisse werden vorausgesetzt",
    "Fluent in English and German.",
    "German - Fluent (C1)",
])
def test_hard_german(text):
    assert hard_drop("Wir bauen KI.\n" + text)


@pytest.mark.parametrize("text", [
    "Sie sprechen fließend Englisch und verstehen Deutsch.",
    "Du sprichst fließend Englisch (gute Deutschkenntnisse sind ein Plus).",
    "C1-Deutschkenntnisse sind von Vorteil, B2-Niveau ist ausreichend.",
    "Du sprichst fließend Deutsch (mindestens B1-2) und Englisch",
    "Deutsch: Sehr gute Kenntnisse in Wort und Schrift, mindestens B2, bevorzugt C1",
    "English is our working language.",
    "", None,
])
def test_not_hard_german(text):
    assert not hard_drop(text)


def test_a_requirement_inside_a_long_unsplit_chunk_is_found():
    # Until 2 Oct 2026 a sentence over 220 characters was skipped, because the old rule tied a level
    # to German by distance. A bullet list that arrived flattened was one such sentence, and that is
    # how "Verhandlungssichere Deutsch- und Englischkenntnisse" got through (Akkodis, Orizon). The
    # level is now tied to the word next to it, so the length of the sentence does not matter.
    blob = "Docker, Kubernetes " * 20 + "sehr gute Deutschkenntnisse " + "x " * 60
    assert hard_drop(blob)
    assert not hard_drop("Docker, Kubernetes " * 20 + "sehr gute Englischkenntnisse, Deutschland " + "x " * 60)


@pytest.mark.parametrize("text", [
    "Strong track record in German automotive industry.",
    "Excellent working knowledge of the German market.",
    "We are a strong German deep-tech startup.",
    "Fluent German or English required.",
    "Strong German skills are not a must.",
])
def test_review_false_drops(text):
    assert not hard_drop(text)


def test_skills_phrasing_still_drops():
    assert hard_drop("You have excellent German and English communication skills.")
    assert hard_drop("Very good German language skills are required.")


# "Sehr gute" can govern two nouns at once, so the German requirement need not sit directly after
# it. BaehrBots, 29 Sep 2026: band() scored this A and the job was only caught by reading the text.
@pytest.mark.parametrize("text", [
    "Sehr gute Englischkenntnisse und Deutschkenntnisse",
    "Sehr gute Englischkenntnisse sowie Deutschkenntnisse",
    "Ausgezeichnete Englischkenntnisse und Deutschkenntnisse",
])
def test_band_drops_sehr_gute_across_two_languages(text):
    assert band("Wir bauen KI-Agenten.\n" + text)[0] == "drop"


# The same shape with English alone must stay out of the drop band.
@pytest.mark.parametrize("text", [
    "Sehr gute Englischkenntnisse in Wort und Schrift",
    "Sehr gute Kenntnisse in Python und SQL",
])
def test_band_does_not_drop_on_english_or_skills_only(text):
    assert band("Wir bauen KI-Agenten.\n" + text)[0] != "drop"


# --- 2 Oct 2026: certain drops, unclear lines, and everything else ---------------------------------
# Every line below is from a real posting. The first group must drop unread. The second must stay
# and be handed to the agent with the sentence attached. The third must not be touched.

DROP = [
    # the 30 Sep hand screen
    "German from C1 for confident client communication",                                    # One Thousand
    "Verhandlungssichere Deutsch- und Englischkenntnisse in Wort und Schrift",              # Akkodis, Orizon
    "Du verfügst über Englischkenntnisse sowie sehr gute Deutschkenntnisse (Level B2).",    # APO Data-Service
    "sehr gute Deutschkenntnisse mindestens auf B2-Niveau sowie exzellente Englischkenntnisse auf C1-Niveau",  # statworx
    # lines the old rule missed, found in the full texts of 2 Oct
    "Fluency in English and German required.",                                              # Celonis
    "Excellent German and English.",
    "Business-fluent command of German and English, both written and spoken",
    "Fluency in both English and German (written and spoken), and willingness to travel regularly",
    "Please note that for this role, C2 German proficiency is required.",
    "Deutschkenntnisse auf muttersprachlichem Niveau (mindestens C1) sowie sehr gute Englischkenntnisse in Wort und Schrift",
    "Language Fluency: Full professional proficiency in both German and English",
    "Exzellente Sprachkenntnisse in Deutsch und Englisch;",
    "Kommunikation: Du kannst dich in der deutschen Sprache fließend und sicher unterhalten.",
    "Very good language skills in German and English",
    "Fließende Kommunikationsfähigkeit auf Deutsch und Englisch sowie Reisebereitschaft",
    # quoted in past rejections and missed by the old rule
    "Deutschkenntnisse mind. C1 in Wort und Schrift",
    "C1+ German for client communication",
    "Volle Sprachgewandtheit in Deutsch und Englisch",
    "sehr gute Kommunikationsfähigkeiten in deutscher und englischer Sprache",
    "Sichere Kommunikation in Deutsch und Englisch sowohl in Wort als auch in Schrift (beide Sprachen min. C1 Level)",
    "verfuegst ueber Deutschkenntnisse auf min. C1-Niveau",
    "Verhandlungssicheres Englisch; Deutsch auf professionellem Niveau",
    "Du beherrschst Deutsch auf mind. C1 Niveau und kannst es erfolgreich im Berufsalltag einsetzen",
    "Gute Deutschkenntnisse (C1-Niveau)",
    "kommunizierst sicher auf Deutsch (C1) sowie Englisch (B2)",
    "Du kannst mindestens auf C1-Level mündlich und schriftlich Deutsch sprechen.",
    # B2 is a drop (the candidate, 2 Oct 2026)
    "Deutsch und Englisch mindestens auf B2-Niveau, sicher in der mündlichen und schriftlichen Kommunikation",
    "Fließende Kommunikationsfähigkeiten in englischer Sprache sowie gute Deutschkenntnisse mindestens auf sicherem B2 Niveau",
    "Du sprichst sehr gutes Deutsch und Englisch (Level B2 - C1)",
    "Sprache: Du sprichst sicher Deutsch (B2/C1/C2-Niveau) und hast gute Englischkenntnisse",
    "Exzellente Englischkenntnisse sowie Deutschkenntnisse mindestens auf B2- Niveau",
    # "runden dein Profil ab" is a requirement, not a softener (the candidate, 2 Oct 2026)
    "Sehr gute Deutschkenntnisse runden dein Profil ab",                                     # Deutsche Bahn
    "Ihr Profil wird durch sehr gute Deutsch- und Englischkenntnisse in Wort und Schrift abgerundet",
    "Fließende Deutsch - und Englischkenntnisse in Wort und Schrift runden dein Profil ab",  # Reply
    "Sprachkompetenz: Sehr gute Deutschkenntnisse (mind. C1) sowie gute Englischkenntnisse runden dein Profil ab.",   # inovex
    # found in the outcome list of 2 Oct
    "Fluent / Business German speaker",                                                      # Almetra
    "Sehr gute und verhandlungssichere (C1) Deutsch- und Englischkenntnisse werden vorausgesetzt",   # NTT DATA
    "Native or near-native proficiency in German and ability to follow detailed written instructions in English.",
    "Verhandlungssicheres Englisch und Deutsch in Wort und Schrift sind zwingend erforderlich.",
    "Gute Deutschkenntnisse (mind. C1) und gute Englischkenntnisse",
    # a softener about something else in the sentence does not soften the German
    "Sehr gute Deutsch- und Englischkenntnisse, weitere Fremdsprachenkenntnisse von Vorteil",
    ("Themenrelevante Praxiserfahrung im In- oder Ausland, idealerweise in einem Beratungsunternehmen, sowie "
     "Reisebereitschaft und sehr gute Deutsch- und Englischkenntnisse in Wort und Schrift"),
    "Fluent German and English, experience with AWS is a plus",
    "Fluent in English, German and French",
    "Deutsch und Englisch, jeweils fließend",
]

DECIDE = [
    "Please note that for this role a C2 proficiency in German, Italian or French is required.",
    "Excellent verbal and written communication skills in both, English and German.",
    "C1-Deutschkenntnisse sind von Vorteil, B2-Niveau ist ausreichend.",
    "Du sprichst fließend Deutsch (mindestens B1-2) und Englisch",
    "Deutsch: Sehr gute Kenntnisse in Wort und Schrift, mindestens B2, bevorzugt C1",
    "gute Deutschkenntnisse (Niveau B2) sind erwünscht",
    "Working knowledge of German at a business level",
    "working language is German",
    "German is the working language in our project",
    "Kommunikationsstark in Deutsch & Englisch",
    "Strong verbal and written communication skills in German and English.",
    "Strong communication and presentation skills in German as well as in English",
    "Advanced German skills",
    "Nice to have\n• Fluent German",
]

KEEP = [
    "English (C1+)",                                                                        # WhyBrilliant
    "Englisch (C1+), Deutsch von Vorteil",
    "Dein Profil\n• Sehr gute Englischkenntnisse\nEin Plus\n• Erfahrung mit n8n\n• Deutschkenntnisse",   # BaehrBots
    # "sicher" stays Band B (the candidate, 2 Oct 2026): adesso, Skaylink, Capgemini Engineering, OSB
    "Sprachkenntnisse: Du kommunizierst mündlich als auch schriftlich sicher und präzise auf Deutsch und Englisch",
    "Sichere Deutsch- und Englischkenntnisse",
    "kommunizierst sicher auf Deutsch und verfügst über Englischkenntnisse",
    "Du kommunizierst sicher auf Deutsch, Englisch ist ein Plus",
    "Sie sprechen fließend Englisch und verstehen Deutsch.",
    "Du sprichst fließend Englisch (gute Deutschkenntnisse sind ein Plus).",
    "You speak fluent English; German is a plus.",
    "fluent English, German is a plus",
    "Fluent in English; German is highly beneficial.",
    "Excellent communication skills in English (German is a strong plus), enabling clear interaction",
    "Fluent German or English required.",
    "Sehr gute Deutsch- oder Englischkenntnisse",
    "Gute Deutsch- und Englischkenntnisse",
    "Du bringst gute Deutschkenntnisse und sehr gute Englischkenntnisse mit.",
    "Good German skills and fluent English",
    "sehr gute Englischkenntnisse (C1), gute Deutschkenntnisse (B1)",
    "Englisch fließend, Deutsch Grundkenntnisse",
    "Sie verfügen über gute Englischkenntnisse auf mindestens B2-Niveau",
    "Sehr gute Englischkenntnisse in Wort und Schrift",
    "sehr gute Englischkenntnisse sowie die Bereitschaft, Deutsch zu lernen",
    "Fließende Englischkenntnisse sind erforderlich; Deutsch oder andere europäische Sprachen sind ein Plus.",
    "Excellent English and preferably German presentation and writing skills",
    "Proficiency in German, Italian, French or Portuguese is a plus.",
    "German at any level.",
    "Strong German skills are not a must.",
    "Strong track record in German automotive industry.",
    "Excellent working knowledge of the German market.",
    "We are a strong German deep-tech startup.",
    "Learn and experience German culture first hand by joining our free German language classes",
    "Celonis is headquartered in Munich, Germany, and New York City, USA, with more than 20 offices worldwide.",
    "Sehr gute Kenntnisse in Python und SQL",
    "English is our working language.",
]


@pytest.mark.parametrize("line", DROP)
def test_certain_german_requirement_drops(line):
    assert german("Wir bauen KI.\n" + line)[0] == "drop"
    assert hard_drop("Wir bauen KI.\n" + line) and not to_decide(line)


@pytest.mark.parametrize("line", DECIDE)
def test_unclear_german_line_goes_to_the_agent(line):
    verdict, lines = german("Wir bauen KI.\n" + line)
    assert verdict == "decide" and lines
    assert not hard_drop(line) and to_decide(line) and band(line)[0] == "decide"


@pytest.mark.parametrize("line", KEEP)
def test_a_plus_or_a_level_he_has_is_left_alone(line):
    assert german("Wir bauen KI.\n" + line)[0] == "ok"
    assert not hard_drop(line) and not to_decide(line) and band(line)[0] in ("A", "B")


def test_a_posting_that_demands_german_and_calls_it_a_plus_is_unclear():
    text = "Requirements\n• Fluent German\n\nAbout the team\nWe work in English, German is a plus."
    assert german(text)[0] == "decide" and len(to_decide(text)) == 2


def test_a_long_flattened_posting_is_fast():
    import time
    flat = ("Docker Kubernetes sehr gute Erfahrung excellent strong " * 2000) + "Deutschkenntnisse C1"
    t = time.time()
    assert german(flat)[0] == "drop" and time.time() - t < 3


def test_a_flattened_list_is_split_at_its_item_marks():
    # Akkodis and Orizon, as the old collector stored them: one line, items joined by " - " or " * ".
    flat = ("Ihr Profil: - Studium der Informatik - Kenntnisse in Kubernetes wünschenswert - Sichere Anwendung von Git "
            "- Verhandlungssichere Deutsch- und Englischkenntnisse in Wort und Schrift - Reisebereitschaft")
    assert hard_drop(flat) == "Verhandlungssichere Deutsch- und Englischkenntnisse in Wort und Schrift"
    star = "Stellenbeschreibung * Python ist von Vorteil * Verhandlungssichere Deutsch- und Englischkenntnisse * Teamgeist"
    assert hard_drop(star)
    assert hard_drop("German - Fluent (C1)")


def test_an_unrelated_soft_word_elsewhere_does_not_make_a_drop_unclear():
    # Kassenärztliche Vereinigung, 2 Oct 2026: "sufficient German" in the visa note is not "German is a plus".
    text = ("Deutschkenntnisse auf muttersprachlichem Niveau (mindestens C1) sowie sehr gute Englischkenntnisse\n"
            "Unfortunately, applications without a valid work permit and sufficient German language skills may not be considered.")
    assert german(text)[0] == "drop"


def test_the_quote_of_a_long_flattened_sentence_shows_the_german_part():
    flat = "Docker Kubernetes Terraform " * 30 + "sowie verhandlungssicheres Deutsch vorausgesetzt " + "Python SQL " * 40
    line = hard_drop(flat)
    assert "verhandlungssicheres Deutsch" in line and len(line) < 300


# --- 3 Oct 2026 (the candidate): drop on German only when the requirement is confirmed -------------------
# A strong German line drops a job by itself only in running text or under a known requirements
# heading. Under a heading the code does not know, the agent decides. Deepslate (fit 8) was rejected
# on 5 Oct because "Nice-to-Haves:" (plural) was not known, and a university post because
# "Wünschenswerte Qualifikationen:" (with non-breaking spaces) was not.

FLUENT = "• Fluent German skills (spoken and written)."
C1 = "• Verhandlungssichere Kenntnisse der deutschen Sprache (C 1) und sehr gute Kenntnisse der englischen Sprache (B2)"


def _under(head, line):
    from lang_band import german
    return german("We build speech models in Berlin.\n%s\n• 3+ years of PyTorch\n%s\nWhat we offer:\n• Salary" % (head, line))[0]


def test_deepslate_plural_nice_to_haves_is_not_a_drop():
    assert _under("Nice-to-Haves:", FLUENT) == "decide"
    assert _under("Nice to haves", FLUENT) == "decide"


def test_an_unknown_heading_goes_to_the_agent():
    assert _under("Extras:", FLUENT) == "decide"
    assert _under("Sonstiges", C1) == "decide"


def test_a_known_requirements_heading_still_drops():
    for head in ("Requirements:", "Your profile", "Dein Profil", "What you bring", "Was du mitbringst",
                 "## Erforderliche Qualifikationen:", "Required qualifications"):
        assert _under(head, FLUENT if "rforderliche" not in head else C1) == "drop", head


def test_a_desirable_qualifications_heading_is_not_a_drop():
    assert _under("## Wünschenswerte Qualifikationen:", C1) == "decide"
    assert _under("Preferred qualifications", FLUENT) == "decide"


def test_running_text_still_drops():
    from lang_band import german
    assert german("You need fluent German skills to talk to our clients every day in the office.")[0] == "drop"
