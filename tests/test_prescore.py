import datetime

import prescore as P

TODAY = datetime.date(2026, 9, 29)


def s(**j):
    return P.score(j, TODAY)[0]


def test_order_keeps_every_row():
    rows = [dict(title="Werkstudent Marketing"), dict(title="Computer Vision Engineer"), dict(title=None), dict()]
    out = P.order(rows, TODAY)
    assert len(out) == 4
    assert out[0]["title"] == "Computer Vision Engineer"


def test_generic_audio_word_needs_an_ml_word():
    assert s(title="Elektroniker für Geräte und Systeme (m/w/d) mit Audio") < s(title="Machine Learning Engineer, Audio")
    assert s(title="IT-Techniker (m/w/d) Schwerpunkt Audio-/Videoausstattung", desc="x") <= 0


def test_specific_phrases_count_alone():
    assert s(title="Computer Vision Engineer", desc="x") >= 4
    assert s(title="Speech Recognition Engineer", desc="x") >= 4


def test_referral_bonus_needs_an_ml_title():
    ml = s(title="Data Scientist AI (D/F/M)", referral=True, desc="x")
    sec = s(title="Director Information Security", referral=True, desc="x")
    assert ml - s(title="Data Scientist AI (D/F/M)", desc="x") == 10
    assert sec == s(title="Director Information Security", desc="x")


def test_member_of_technical_staff_is_not_a_staff_title():
    assert s(title="Member of Technical Staff (Machine Learning Research Engineer)", desc="x") > 0
    assert s(title="Staff Machine Learning Engineer", desc="x") < s(title="Machine Learning Engineer", desc="x")


def test_infra_core_needs_two_terms():
    one = s(title="ML Engineer", desc="pytorch fsdp")
    two = s(title="ML Engineer", desc="pytorch fsdp slurm")
    assert two == one - 3


def test_no_desc_bonus_only_for_matching_titles():
    assert s(title="Projektmanager Marketing") <= 0


def test_freshness_and_bad_dates():
    fresh = s(title="ML Engineer", desc="x", date="2026-09-28")
    old = s(title="ML Engineer", desc="x", date="2025-01-01")
    assert fresh > old
    for d in ("", None, "not a date", "2026-13-45"):
        s(title="ML Engineer", desc="x", date=d)       # must not raise


def test_linkedin_and_berlin_bonus():
    base = s(title="ML Engineer", desc="x")
    assert s(title="ML Engineer", desc="x", source="linkedin") == base + 2
    assert s(title="ML Engineer", desc="x", location="Berlin, Germany") == base + 1


def test_any_ai_title_scores_like_ml():
    ml = s(title="Machine Learning Engineer", desc="x")
    for t in ("AI Engineer", "AI Associate", "Software Architekt AI (m/w/d)", "KI-Entwickler (m/w/d)", "Agentic AI Developer"):
        assert s(title=t, desc="x") >= ml, t


def test_company_name_in_title_is_not_a_job_word():
    t = "Director Information Security, DHL Data & AI (d/f/m)"
    assert s(title=t, company="DHL Data & AI", referral=True, desc="x") < 0
    assert s(title="Data Scientist AI (D/F/M), DHL Data & AI", company="DHL Data & AI", referral=True, desc="x") >= 10


def test_terms_do_not_match_inside_words():
    plain = s(title="ML Engineer", desc="nothing relevant here")
    noisy = s(title="ML Engineer", desc="support opportunity simulation minimum began Morgan laws Agentur")
    assert noisy == plain
    assert s(title="Research Scientist, Security Division", desc="x") < s(title="Research Scientist, Computer Vision", desc="x")
