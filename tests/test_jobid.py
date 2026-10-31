import pytest

from jobid import is_repeat, named_in, same_company

SEEN = [
    dict(id="gema", company="GEMA", title="AI Engineer (m/w/d)", location="Berlin or München (Vor Ort)", url="https://a/1", sent="2026-09-11"),
    dict(id="handly", company="handly", title="Founding AI Engineer", location="Berlin-Mitte", url="https://a/2", sent="2026-09-11"),
    dict(id="fzj", company="Forschungszentrum Jülich (Jülich Supercomputing Centre)",
         title="Research Software Engineer – AI and Earth Observation", location="Jülich", url="https://a/3", sent="2026-09-16"),
    dict(id="arrk", company="ARRK Engineering GmbH", title="Machine Learning Engineer Automatisiertes Fahren (m/w/d)",
         location="München", url="https://a/4", sent="2026-09-06"),
    dict(id="huk", company="HUK-COBURG", title="(Senior) Applied Scientist (Machine Learning) (w/m/d)",
         location="Coburg", url="https://a/5", sent="2026-09-14"),
    dict(id="smartly", company="Smartly (smartly.io)", title="Senior Machine Learning Engineer, AI Platform",
         location="Berlin", url="https://a/6", sent="2026-09-20"),
    dict(id="stark", company="STARK", title="Data & Machine Learning Engineer (All genders)", location="Berlin", url="https://a/7", sent="2026-08-20"),
    dict(id="ig", company="Innovation Group GmbH", title="AI Engineer (m/w/d)", location="Stuttgart", url="https://a/8", sent="2026-09-27"),
    dict(id="microagi", company="microagi", title="Depth Research Engineer", location="Munich", url="https://microagi.ai/careers", sent="2026-08-08"),
]


@pytest.mark.parametrize("company,title,desc", [
    ("GEMA - Gesellschaft für musik. Aufführungs- und mechan. Vervielfältigungsrechte", "AI Engineer (m/w/d) - Vor Ort", ""),
    ("handly", "Founding AI Engineer @handly - 20VC backed", ""),
    ("Forschungszentrum Jülich GmbH P-VA Personalabrechnung", "Research Software Engineer - AI and Earth Observation", ""),
    ("Mitsui Chemicals Group", "Machine Learning Engineer Automatisiertes Fahren (m/w/d)", "GESELLSCHAFT ARRK Engineering GmbH. Wir suchen"),
    ("Mecklenburgische Versicherungs-Gesellschaft a. G.", "(Senior) Applied Scientist (Machine Learning) (w/m/d)", "HUK-COBURG Versicherungsgruppe. Als einer"),
    ("", "Senior Machine Learning Engineer, AI Platform", "Smartly is the AI-powered advertising platform"),
])
def test_leaked_repeats_now_match(company, title, desc):
    assert is_repeat(company, title, "", SEEN, "", desc)


@pytest.mark.parametrize("company,title,desc", [
    # a different role at a sent company
    ("GEMA", "Data Engineer (m/w/d)", ""),
    # the German adjective "stark" must not name STARK
    ("PROCITEC GmbH", "Machine Learning Engineer (m/w/d)", "Wir sind stark im Bereich Signalverarbeitung."),
    # "innovation" is in half the adverts; Innovation Group is only named by its full name
    ("opta data Gruppe", "AI-Engineer (w/m/x)", "Innovation ist unser Antrieb."),
    # microagi: two different roles on one careers page
    ("microagi", "SLAM Research Engineer", ""),
    # empty and None inputs
    ("", "", ""),
    (None, None, None),
])
def test_not_repeats(company, title, desc):
    assert not is_repeat(company, title, "", SEEN, "", desc)


def test_named_in_rules():
    assert named_in("STARK", "Join STARK in Berlin")
    assert not named_in("STARK", "wir sind stark")
    assert named_in("Innovation Group GmbH", "About Innovation Group: we build")
    assert not named_in("Innovation Group GmbH", "Innovation drives us")
    assert not named_in("", "anything")
    assert not named_in("AB", "AB is a company")          # too short to trust


def test_admin_suffix_does_not_break_normal_names():
    assert same_company("Forschungszentrum Jülich GmbH P-VA Personalabrechnung", "Forschungszentrum Jülich")
    assert not same_company("Personio", "Forschungszentrum Jülich")


# Review of 29 Sep 2026: customer and tool names in a description must not make a repeat.
SEEN_REVIEW = SEEN + [
    dict(id="dev", company="develop (Developrec, recruiter - client not named)", title="Senior Agentic AI Engineer",
         location="Munich", url="https://a/9", sent="2026-09-10"),
    dict(id="finn", company="FINN", title="Data Scientist", location="Munich", url="https://a/10", sent="2026-09-10"),
]


@pytest.mark.parametrize("company,title,loc,desc", [
    ("Acme Robotics GmbH", "Agentic AI Engineer (m/w/d)", "Munich", "You develop LLM agents."),
    ("Foo Analytics", "Data Scientist (m/w/d)", "Munich", "At Foo Analytics our clients include FINN and Sixt."),
    ("", "Data Scientist (m/w/d)", "Hamburg", "FINN is hiring in Munich."),          # places disagree
])
def test_customer_or_word_in_description_is_not_a_repeat(company, title, loc, desc):
    assert not is_repeat(company, title, loc, SEEN_REVIEW, "", desc)


def test_blank_company_still_matches_by_description():
    assert is_repeat("", "Data Scientist", "Munich", SEEN_REVIEW, "", "FINN is Munich's car subscription company.")


from jobid import same_role


@pytest.mark.parametrize("a,b,co,strict,loose", [
    ("Senior AI Software Engineer", "Senior AI Software Engineer, req 11563", "NiCE", True, True),
    ("Data Scientist (w/m/d)", "Data Scientist (w/m/d) - 7641", "TÜV SÜD", True, True),
    ("Senior Machine Learning Engineer - (Logistics, Optimization)", "Senior Machine Learning Engineer, Logistics Optimization", "Delivery Hero", False, True),
    ("AI Software Engineer, Imitation Learning", "AI Software Engineer, Reinforcement Learning (f/m/d)", "TACTILIA Robotics", False, True),
    ("Team Lead MLOps (D/F/M)", "Data Scientist AI (D/F/M)", "DHL Data & AI", False, False),
])
def test_same_role(a, b, co, strict, loose):
    assert same_role(a, b, co) is strict
    assert same_role(a, b, co, loose=True) is loose


def test_linkedin_footer_and_city_aliases():
    # review, 29 Sep 2026: real LinkedIn descriptions end with the posting account's name
    foot = " Referrals increase your chances of interviewing at Mitsui Chemicals Group. Get notified about new jobs."
    assert is_repeat("Mitsui Chemicals Group", "Machine Learning Engineer Automatisiertes Fahren (m/w/d)",
                     "Munich, Bavaria, Germany", SEEN, "https://li/1",
                     "GESELLSCHAFT ARRK Engineering GmbH Wir suchen dich." + "x " * 400 + foot)


def test_all_stored_links_and_ba_ref_match():
    seen = [dict(id="c24", company="CHECK24 AI Forge", title="(Junior) Data Scientist (m/w/d) Search / AI Forge",
                 url="https://jobs.check24.de/", urls=["https://www.arbeitsagentur.de/jobsuche/jobdetail/20208-be7978831d1446cfb20-S"])]
    assert is_repeat("CHECK24 Services Personal GmbH", "Something else entirely", "", seen,
                     "https://www.arbeitsagentur.de/jobsuche/jobdetail/20208-be7978831d1446cfb20-S")


def test_employer_named_with_at_in_title():
    seen = [dict(id="b", company="Briink", title="Product Engineer (Backend/AI)", location="Berlin", url="https://b/1")]
    assert is_repeat("Merantix", "Product Engineer (Backend/AI) @Briink", "Berlin", seen, "https://m/2")


def test_language_parameter_and_city_list_do_not_hide_a_repeat():
    # review of the 29 Sep unread rows: Briink came back with ?language=en and "Berlin, London"
    seen = [dict(id="b", company="Briink", title="Product Engineer (Backend/AI) @Briink",
                 url="https://briink.jobs.personio.com/job/2777150")]
    assert is_repeat("Briink", "Product Engineer (Backend/AI) @Briink Berlin, London", "", seen,
                     "https://briink.jobs.personio.com/job/2777150?language=en")


def test_norm_url_keeps_job_identifying_parameters():
    from jobid import norm_url
    assert norm_url("https://de.talent.com/view?id=abc&utm_source=x") == "https://de.talent.com/view?id=abc"
    assert norm_url("https://x.io/job/1?language=en&gh_jid=55") == "https://x.io/job/1?gh_jid=55"


# 29 Oct 2026: five repeats the runs of 25 to 29 Oct caught by hand (docs/CODE_ISSUES.md). Each row below
# is the card as it reached the radar, each SEEN_OCT entry the job as state/seen.json held it.
from jobid import norm_title, same_title, strip_board_tail, title_in_desc

HORNET_TEXT = ("Wir suchen für unseren Standort in Hannover ab sofort einen Data Engineer/Software Engineer (m/w/d) "
               "zur Verstärkung unseres Teams. Du entwickelst robuste Software- und Datenlösungen.")
HEIGIT_TEXT = ("HeiGIT (Heidelberg Institute for Geoinformation Technology) As a nonprofit research institute, HeiGIT bridges "
               "the gap between geoinformatics research and real-world applications. " * 3 +
               "We are looking for a Senior Machine Learning Engineer, with focus on GeoAI for Humanitarian Applications, "
               "to join our team in Heidelberg as soon as possible.")
HUK_TEXT = "HUK-COBURG Versicherungsgruppe (Senior) Engineer Machine Learning / AI (w/m/d) Coburg Aufgabe Konzeption und Umsetzung"
SEEN_OCT = [
    dict(id="hornet", company="Hornetsecurity (Proofpoint Hornet GmbH)", title="Data Engineer / Software Engineer (m/w/d)",
         location="Hannover, Germany", url="https://hornetsecurity.jobs.personio.de/job/2797442"),
    dict(id="huk", company="HUK-COBURG Versicherungsgruppe", title="Wir suchen: (Senior) Engineer Machine Learning / AI (w/m/d)",
         location="Coburg, Bavaria, Germany", url="https://www.huk.de/karriere/einstieg/x.html", urls=["https://de.talent.com/view?id=b3be3fe363f7"]),
    dict(id="parship", company="Parship", title="(Junior) Machine Learning Engineer (all genders) - Anwendungsentwicklung, Ingenieur",
         location="Berlin", url="https://www.get-in-it.de/jobsuche/p311622", urls=["https://de.talent.com/view?id=b548da021618"]),
    dict(id="heigit", company="HeiGIT gGmbH", title="Senior Machine Learning Engineer (m/f/d) -  GeoAI for Humanitarian Applications",
         location="Heidelberg", url="https://heigit.org/careers/"),
    dict(id="sumup", company="SumUp", title="Senior Machine Learning Engineer I", location="Berlin",
         url="https://sumup.com/careers/positions/8498275002?gh_jid=8498275002"),
    dict(id="elac", company="ELAC SONAR GmbH", title="AI Platform Engineer (m/w/d)", location="Kiel",
         url="https://de.linkedin.com/jobs/view/ai-platform-engineer-m-w-d-at-elac-sonar-gmbh-4482445884"),
]


@pytest.mark.parametrize("company,title,loc,url,desc,want", [
    ("Hornetsecurity", "Data Engineer", "Hannover", "https://de.linkedin.com/jobs/view/4467725584", HORNET_TEXT, "hornet"),
    ("Mecklenburgische Versicherungs-Gesellschaft a. G.", "(Senior) Engineer Machine Learning / AI (w/m/d)", "Coburg",
     "https://de.linkedin.com/jobs/view/4483342783", HUK_TEXT, "huk"),
    ("HUK-COBURG", "(Senior) Engineer Machine Learning / AI (w/m/d)", "Coburg", "https://de.linkedin.com/jobs/view/4483342783", "", "huk"),
    ("Parship", "(Junior) Machine Learning Engineer (all genders)", "Berlin", "https://www.arbeitsagentur.de/jobsuche/jobdetail/13644-311622-S", "", "parship"),
    ("HeiGIT (Heidelberg Institute for Geoinformation Technology)", "Data Engineer - Machine Learning (m/f/d)", "Heidelberg",
     "https://de.linkedin.com/jobs/view/4481886760", HEIGIT_TEXT, "heigit"),
    ("Sumup", "AI / Machine Learning Engineer II", "Berlin", "https://de.talent.com/view?id=ddac088e13c9", "", "sumup"),
    ("ELAC SONAR GmbH", "AI Platform Engineer (m/w/d) - LLMs & On-Premises gesucht", "Kiel", "https://de.talent.com/view?id=aa77489b07a5", "", "elac"),
])
def test_repeats_caught_by_hand_in_october_now_match(company, title, loc, url, desc, want):
    m = is_repeat(company, title, loc, SEEN_OCT, url, desc)
    assert m and m["id"] == want


@pytest.mark.parametrize("company,title,loc,desc", [
    # same company, the sent title's words in the text but as a plural, in a sentence about the team
    ("Hornetsecurity", "Head of AI", "Hannover", "Wir suchen einen Head of AI. Du führst unsere Data Engineers und Software Engineers."),
    # the sent title named in the text, but the card title shares no word with it
    ("Hornetsecurity", "Head of AI", "Hannover", HORNET_TEXT),
    # same words, wrong order
    ("Hornetsecurity", "Data Engineer", "Hannover", "Wir suchen einen Software Engineer für unser Data Engineer Team."),
    # the sent title in the text, but another city
    ("Hornetsecurity", "Data Engineer", "München", HORNET_TEXT),
    # a second role at a sent company, plain title, no text
    ("SumUp", "Senior Data Engineer II", "Berlin", ""),
    ("ELAC SONAR GmbH", "Embedded Software Engineer (m/w/d) gesucht", "Kiel", ""),
    # a get-in-it style tail on a different role
    ("Parship", "(Junior) Data Engineer (all genders) - Anwendungsentwicklung, Ingenieur", "Berlin", ""),
])
def test_october_rules_do_not_fuse_different_roles(company, title, loc, desc):
    assert not is_repeat(company, title, loc, SEEN_OCT, "https://x/new", desc)


@pytest.mark.parametrize("a,b", [
    ("Wir suchen: (Senior) Engineer Machine Learning / AI (w/m/d)", "(Senior) Engineer Machine Learning / AI (w/m/d)"),
    ("Wir suchen einen Machine Learning Engineer", "Machine Learning Engineer"),
    ("Gesucht: Data Scientist (m/w/d)", "Data Scientist"),
    ("We are looking for a Data Scientist", "Data Scientist"),
    ("Stellenangebot: Softwareentwickler KI", "Softwareentwickler KI"),
    ("AI Platform Engineer (m/w/d) - LLMs & On-Premises gesucht", "AI Platform Engineer"),
    ("Data Scientist (m/w/d) gesucht!", "Data Scientist"),
    ("Senior Data Scientist - Pricing gesucht", "Data Scientist"),
    ("Software Engineer II", "Senior Software Engineer"),
    ("AI / Machine Learning Engineer II", "AI Machine Learning Engineer"),
])
def test_lead_ins_wanted_tails_and_levels_are_noise(a, b):
    assert norm_title(a) == norm_title(b)


@pytest.mark.parametrize("a,b", [
    ("Job Architect", "Architect"),                       # a one-word lead-in needs its colon
    ("Jobs Data Engineer", "Data Engineer"),
    ("AI Engineer", "Engineer"),                          # "ai" is not the level "i"
    ("Research Scientist - World Models", "Research Scientist"),
])
def test_what_is_not_a_lead_in(a, b):
    assert norm_title(a) != norm_title(b)


def test_board_category_tail_only_with_a_get_in_it_link():
    t = "(Junior) Machine Learning Engineer (all genders) - Anwendungsentwicklung, Ingenieur"
    assert strip_board_tail(t, ["https://www.get-in-it.de/jobsuche/p311622"]) == "(Junior) Machine Learning Engineer (all genders)"
    assert strip_board_tail(t, ["https://de.talent.com/view?id=1"]) == t
    for keep in ("Research Scientist - World Models", "Senior Machine Learning Engineer (m/f/d) - GeoAI for Humanitarian Applications",
                 "AI - Engineer"):
        assert strip_board_tail(keep, ["https://www.get-in-it.de/jobsuche/p1"]) == keep


def test_title_in_desc_rules():
    sent = "Senior Machine Learning Engineer (m/f/d) - GeoAI for Humanitarian Applications"
    assert title_in_desc(sent, "Data Engineer - Machine Learning (m/f/d)", HEIGIT_TEXT)
    assert not title_in_desc(sent, "Data Engineer - Machine Learning (m/f/d)", HEIGIT_TEXT, head=600)   # the sentence sits at 700
    assert not title_in_desc(sent, "Data Engineer - Machine Learning (m/f/d)", "")
    assert not title_in_desc("Data Engineer", "Data Engineer", HORNET_TEXT)                              # two tokens are too few
    assert title_in_desc("Data Engineer / Software Engineer (m/w/d)", "Data Engineer", HORNET_TEXT)
    assert same_title("Software Engineer I", "Software Engineer II")                                     # levels collapse on purpose
