import pytest

import salary


@pytest.mark.parametrize("text,want", [
    ("Einstiegsgehalt : ca. 90.000 € Fixum  Standort : Berlin", "about EUR 90k"),
    ("The Deal: Salary: 85k euro - 160k euro. No fluff", "EUR 85k-160k"),
    ("The salary starts at €120,000 / £120,000 base, plus RSUs.", "from EUR 120k"),
    ("Agentic AI Architect - AI-Native Builder - Berlin OR Remote | €120k   This is not", "EUR 120k"),
    ("Forward-Deployed AI Engineer - Claude Code - €120,000 - Munich - Hybrid", "EUR 120k"),
    ("bieten wir Dir ein Entgelt entsprechend TV-L EG 13.", "TV-L E13 (public pay scale)"),
    ("Vergütung nach TVöD E 13", "TVöD E13 (public pay scale)"),
    ("Salary: EUR 90,000 - 140,000 + Equity", "EUR 90k-140k"),
    ("70.000 - 90.000 EUR brutto", "EUR 70k-90k"),
    ("attraktives Gehalt bis zu 80.000 €", "up to EUR 80k"),
])
def test_extract(text, want):
    assert salary.extract(text) == want


@pytest.mark.parametrize("text", [
    "Gewinnbeteiligung bis zu 24.000 € - 50 € Tank",
    "Bonus up to €20,000 per year",
    "Zuschuss von bis zu 60 € monatlich",
    "over €2 billion market cap",
    "Employee Development Budget of €2,000",
    "Raise a total of €400 million, including from Sequoia",
    "Competitive compensation package",
    "", None,
])
def test_no_salary(text):
    assert salary.extract(text) == ""


def test_ask_table(monkeypatch):
    # This repository ships the table empty; SETUP.md fills it. An empty figure prints no ask line.
    assert salary.ask("startup") == ("", "")
    monkeypatch.setattr(salary, "ASK", dict(salary.ASK, startup=("EUR 55-60k", "r"), large=("EUR 65-75k", "r")))
    assert salary.ask("startup")[0] == "EUR 55-60k"
    assert salary.ask("mid") == ("", "")
    assert salary.ask("recruiter")[0].startswith("the range")
    assert salary.ask("LARGE ")[0] == "EUR 65-75k"


def test_ask_stated_salary_wins_and_unknown_class_is_empty():
    assert salary.ask("startup", "EUR 90k") == ("", "")
    assert salary.ask("", "") == ("", "")
    assert salary.ask(None, None) == ("", "")
    assert salary.ask("megacorp") == ("", "")


def test_profit_share_after_long_prefix():
    # review, 29 Sep 2026: the guard only saw 24 characters, so real text slipped through
    txt = "- unbefristetes Arbeitsverhältnis - attraktives Gehalt - Gewinnbeteiligung bis zu 24.000 € - 50 € Tank"
    assert salary.extract(txt) == ""


def test_ask_with_numeric_salary_does_not_crash():
    assert salary.ask("startup", 90000) == ("", "")
