"""Rejection gates, borderline jobs, and consistency on send (30 Sep 2026)."""
import json
import os
import subprocess
import sys

import pytest

import final_check as F
from conftest import SCRIPTS


# --- which titles reach the candidates ---------------------------------------------------------

TITLES = {
    "Data Engineer": True,                                   # data engineering is wanted
    "Senior Analytics Engineer": True,
    "MLOps Platform Engineer": True,                          # platform, but AI related
    "Senior AI Consultant": True,                             # consulting, but AI related
    "Machine Learning Engineer": True,
    "DevOps Engineer": False,                                 # platform work with no AI or data
    "Senior Frontend Developer": False,
    "Data Analyst": False,                                    # analyst as the whole job
    "Senior Data Analyst - Machine Learning": True,           # analyst with an ML word
    "Engineering Manager, Machine Learning": False,           # management
}


def test_titles_reach_the_candidates_as_intended(tmp_path):
    sc = tmp_path / "sc"
    sc.mkdir()
    for src in ("ba", "getro", "talent", "arbeitnow", "linkedin", "xing", "stepstone"):
        (sc / (src + ".json")).write_text("[]")
    rows = [dict(company="Zz Test Co %d" % i, title=t, location="Berlin, Germany", url="https://zz.example/%d" % i,
                 date="2026-09-29", desc="Python.", source="greenhouse") for i, t in enumerate(TITLES)]
    (sc / "ats.json").write_text(json.dumps(rows))
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "filter_run.py"), str(sc)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-2000:]
    kept = {c["title"] for c in json.load(open(sc / "candidates.json"))}
    assert {t for t, want in TITLES.items() if want} == kept


# --- consistency on send -----------------------------------------------------------------------

def check(tmp_path, jobs):
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    (root / "state/seen.json").write_text("[]")
    (root / "state/applications.md").write_text("")
    sc = tmp_path / "sc"
    sc.mkdir()
    (sc / "shortlist.json").write_text(json.dumps(dict(date="2026-09-30", slot="morning", jobs=jobs)))
    return {r[1]: r[0] for r in F.check(str(sc / "shortlist.json"), root=str(root))}


def job(co, desc, **kw):
    return dict(company=co, title="ML Engineer", apply_url="https://%s.example/1" % co.lower(), desc=desc, **kw)


def test_a_job_with_a_c1_german_line_is_not_sent(tmp_path):
    got = check(tmp_path, [job("Exxeta", "Wir bauen KI. Du sprichst fließend Deutsch und Englisch."),
                           job("Fine", "You build PyTorch models. German is a plus.")])
    assert got == {"Exxeta": "GERMAN", "Fine": "OK"}


def test_a_clearance_rule_blocks_the_send_but_its_negation_does_not(tmp_path):
    got = check(tmp_path, [job("Defence", "Nationality of a NATO member nation is required for this role."),
                           job("Open", "No security clearance required.")])
    assert got == {"Defence": "CLEARANCE", "Open": "OK"}


def test_a_dhl_referral_job_is_exempt(tmp_path):
    got = check(tmp_path, [job("DHL", "Sehr gute Deutschkenntnisse (C1) erforderlich.", referral=True)])
    assert got == {"DHL": "OK"}


def test_the_command_fails_on_a_german_send(tmp_path):
    root = tmp_path
    (root / "state/seen.json").write_text("[]")
    sl = tmp_path / "shortlist.json"
    sl.write_text(json.dumps(dict(date="2026-09-30", slot="morning",
                                  jobs=[job("Exxeta", "Du sprichst fließend Deutsch und Englisch.")])))
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "final_check.py"), str(sl)], capture_output=True, text=True)
    assert r.returncode == 1 and "GERMAN" in r.stdout


# --- borderline jobs count as read ------------------------------------------------------------

def test_borderline_jobs_count_as_read_for_the_backlog_and_the_fresh_check(tmp_path):
    import fresh_check
    import leftover
    sl = dict(date="2026-09-29", borderline=[dict(company="Brainlab", title="Applied AI Engineer", fit=5)])
    assert [r["company"] for r in leftover.read_by(sl)] == ["Brainlab"]
    (tmp_path / "candidates.json").write_text(json.dumps([dict(company="Brainlab", title="Applied AI Engineer",
                                                               date="2026-09-29", url="https://b.example/1")]))
    assert fresh_check.unread_fresh(str(tmp_path), sl) == []


# 2 Oct 2026: an unclear German line may be sent only with the sentence shown in `lang_line`.
UNCLEAR = "We build agents.\nPlease note that for this role a C2 proficiency in German, Italian or French is required."


def test_an_unclear_german_line_needs_the_quote(tmp_path):
    got = check(tmp_path, [job("Reonic", UNCLEAR, lang_line="no language line in the posting"),
                           job("Quoted", UNCLEAR, lang_line="'C2 proficiency in German, Italian or French is required', he has none of the three at C2"),
                           job("Dhl", UNCLEAR, referral=True)])
    assert got == {"Reonic": "GERMAN?", "Quoted": "OK", "Dhl": "OK"}
