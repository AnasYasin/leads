import pytest

import lang_band
import salary
import trim_desc as T


def test_removes_perk_sentences_and_keeps_the_rest():
    d = ("You build detection models in PyTorch. What we offer: Free lunch. Gym membership. 30 days of vacation. "
         "Your profile: 3+ years of Python.")
    new, cut = T.trim(d)
    assert "Free lunch" not in new and "Gym" not in new and "vacation" not in new
    assert "Your profile: 3+ years of Python." in new and "PyTorch" in new
    assert cut > 0


@pytest.mark.parametrize("text", [
    "What you'll do Own and evolve ClickHouse's Python connector and SDK ecosystem.",
    "You will work on recommendation problems with direct, measurable impact.",
    "Führe Nutzerinterviews mit Fachexperten und Wissensmanagern, um das System zu verbessern.",
    "Our mission is to build a modern ecosystem used for all IONOS customer support needs.",
    "We are a team of 200 employees, founded in 2012, headquartered in Munich with a great canteen.",
])
def test_responsibilities_and_company_lines_are_never_removed(text):
    assert T.trim(text)[0] == text


@pytest.mark.parametrize("text,want", [
    ("Svelte) What we offer Competitive salary based on experience (€70,000 - €100,000) Top-tier hardware Your profile Python", "EUR 70k-100k"),
    ("Deutsch Das bieten wir Flexibles Arbeiten 30 Urlaubstage Zielgehalt bis ca. 140.000 EUR BAV, JobRad", "about EUR 140k"),
    ("Benefits: Salary 65.000 - 90.000 EUR. Free drinks.", "EUR 65k-90k"),
])
def test_salary_survives_the_cut(text, want):
    new, _ = T.trim(text)
    assert salary.extract(new) == want


def test_german_line_survives_the_cut():
    d = "Tasks: build models. Wir bieten: Obstkorb. Sehr gute Deutschkenntnisse (C1) erwünscht wären toll. Kicker."
    new, _ = T.trim(d)
    assert "Deutschkenntnisse" in new and "Obstkorb" not in new


@pytest.mark.parametrize("text", [
    "We offer a platform that helps doctors. You will build models.",
    "Erfahrung mit Kubernetes ist von Vorteil. Du entwickelst Modelle.",
    "The benefits of self-supervised learning are clear to us. You build SSL pipelines.",
])
def test_ordinary_sentences_are_not_headings(text):
    assert T.trim(text)[0] == text


def test_diversity_boilerplate_is_removed():
    d = "You build models. We are an equal opportunity employer and value diversity. Apply now."
    new, _ = T.trim(d)
    assert "equal opportunity" not in new and "You build models." in new


@pytest.mark.parametrize("text", ["", None])
def test_empty(text):
    assert T.trim(text) == ("", 0)


def test_hard_drop_unchanged_on_a_real_kill():
    d = "Your profile: Python. Sprachkenntnisse: Sehr gute Deutschkenntnisse (C1-Level). Das bieten wir: Obst."
    assert bool(lang_band.hard_drop(d)) == bool(lang_band.hard_drop(T.trim(d)[0])) is True


@pytest.mark.parametrize("text,must_keep", [
    # review, 29 Sep 2026: bare "diversity" / "diverse" / "inclusive" used to cut these
    ("You will ship models adaptable to a diversity of clients Partner with researchers on evaluation", "diversity of clients"),
    ("Develop metrics to quantify synthetic task diversity and coverage", "task diversity"),
    ("Since 2019 n8n has grown into a diverse team of over 260 people across Europe", "diverse team of over 260"),
    # flattened benefits run-on with an equal-opportunity line inside it
    ("What We Offer Transparent comp with a 50/50 base to variable split, plus equity Comprehensive benefits package "
     "and we are an equal opportunity employer " + "x " * 120, "Transparent comp"),
])
def test_work_and_pay_survive_diversity_rule(text, must_keep):
    assert must_keep in T.trim(text)[0]


def test_real_equal_opportunity_lines_go():
    for line in ["Almedia is an equal opportunity employer.",
                 "Unabhängig von Geschlecht, Alter, ethnischer Herkunft, Religion oder Behinderung sind alle willkommen."]:
        assert line not in T.trim("You build models in PyTorch. " + line + " Your profile: Python.")[0]
