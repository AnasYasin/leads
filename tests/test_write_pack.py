"""write_pack.py run for real in a temporary copy of the repo, with the network stubbed."""
import json
import os
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT

RUNNER = r'''
import sys, json
sys.path.insert(0, "scripts")
import write_pack as W
W.live = lambda u: ("LIVE", "test")
W.true_date = lambda u, t="": (None, "")
sys.argv = ["write_pack.py", sys.argv[1]]
W.main()
'''


@pytest.fixture
def repo(tmp_path):
    shutil.copytree(os.path.join(ROOT, "scripts"), tmp_path / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(os.path.join(ROOT, "config"), tmp_path / "config")
    shutil.copy(os.path.join(ROOT, "state/rejected.json"), tmp_path / "state/rejected.json")
    # Own state/seen.json, so the tests do not depend on entries the real one prunes after 90 days.
    (tmp_path / "state/seen.json").write_text(json.dumps([
        dict(id="arrk", company="ARRK Engineering GmbH", title="Machine Learning Engineer Automatisiertes Fahren (m/w/d)",
             location="München", url="https://arrk.example/job/1", sent="2026-09-06", fit=7),
        dict(id="old", company="Some Old Co", title="Data Scientist", location="Berlin", url="https://old.example/1",
             sent="2026-09-20", fit=6)]))
    for d in ("jobs", "shortlists", "companies"):
        (tmp_path / d).mkdir()
    (tmp_path / "run.py").write_text(RUNNER)
    return tmp_path


def render(repo, sl):
    p = repo / "sl.json"
    p.write_text(json.dumps(sl, ensure_ascii=False))
    r = subprocess.run([sys.executable, "run.py", str(p)], cwd=repo, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return r, (repo / "shortlists" / ("%s-%s.md" % (sl["date"], sl["slot"]))).read_text()


BASE = dict(date="2026-09-29", slot="morning", summary="t", coverage=[], notes="")
JOB = dict(company="Testfirma GmbH", title="Computer Vision Engineer (m/w/d) ZZTEST", location="Berlin", source="linkedin",
           tier=1, fit=8, priority=10, band="A", apply_url="https://example.org/job/zztest-1", cv_base="CV",
           desc="We build PyTorch detection models.", size_class="startup", staff="~20")


def test_no_jobs(repo):
    r, md = render(repo, dict(BASE, jobs=[]))
    assert "0 jobs rendered" in r.stderr


def test_ask_line_and_reading_counts(repo):
    _, md = render(repo, dict(BASE, jobs=[JOB], candidates=300, read_full=40, left_unread=260,
                              unread_by_source={"ats": 200, "linkedin": 0}, rejected_before=5, german_dropped=3, minutes=33))
    assert "Salary: not stated in the posting" in md
    assert "Ask for:" not in md  # This repository ships an empty ask table; test_salary covers a filled one
    assert "Read in full: 40. Left unread: 260 (ats 200)" in md


def test_stated_salary_suppresses_ask(repo):
    _, md = render(repo, dict(BASE, jobs=[dict(JOB, desc="Salary: EUR 90,000 - 110,000.")]))
    assert "Salary: EUR 90k-110k" in md and "Ask for:" not in md


def test_edge_case_jobs_do_not_crash(repo):
    jobs = [dict(JOB, apply_url="https://example.org/job/zz-2", desc=""),                       # no description
            dict(JOB, company="Agency (recruiter, client not named)", title="ML Engineer ZZ3", recruiter=True,
                 size_class="", apply_url="https://example.org/job/zz-3"),
            dict(JOB, title="ML Engineer ZZ4", size_class=None, staff=None, salary=None, apply_url="https://example.org/job/zz-4")]
    r, md = render(repo, dict(BASE, jobs=jobs, rejected=[
        dict(company=None, title=None, fit=None, reason=None),
        dict(company="E2E Firma", title="AI Engineer", fit=7, reason="Drop band: 'Sehr gute Deutschkenntnisse (C1)'.")]))
    assert "3 jobs rendered" in r.stderr
    assert "Ask for: the range, from the recruiter first" in md
    rej = json.load(open(repo / "state/rejected.json"))
    assert any(x["company"] == "E2E Firma" for x in rej)


def test_a_repeat_under_another_company_name_stops_the_render(repo):
    # ARRK, sent 6 Sep, came back as "Mitsui Chemicals Group" in almost every run (docs/PROBLEMS.md 5.2). Until
    # 2 Oct 2026 write_pack.py rendered it and printed PRIOR SAME ROLE, and the email went out. Now the final
    # check is part of the render: nothing is written, so there is no second, corrected email (5.6).
    j = dict(JOB, company="Mitsui Chemicals Group", title="Machine Learning Engineer Automatisiertes Fahren (m/w/d)",
             location="München", desc="GESELLSCHAFT ARRK Engineering GmbH. Wir suchen", apply_url="https://example.org/job/zz-5")
    p = repo / "sl.json"
    p.write_text(json.dumps(dict(BASE, jobs=[j]), ensure_ascii=False))
    r = subprocess.run([sys.executable, "run.py", str(p)], cwd=repo, capture_output=True, text=True, timeout=120)
    assert r.returncode != 0 and "REPEAT" in r.stderr and "ARRK" in r.stderr and "REFUSED" in r.stderr
    assert not list((repo / "shortlists").iterdir()) and not list((repo / "jobs").iterdir())


def test_string_and_odd_unread_counts(repo):
    _, md = render(repo, dict(BASE, jobs=[JOB], candidates="300", read_full="40", left_unread="260",
                              unread_by_source={"linkedin": "12", "ats": None, "xing": [1]}))
    assert "Left unread: 260 (linkedin 12)" in md


def test_unread_by_source_not_a_dict(repo):
    _, md = render(repo, dict(BASE, jobs=[JOB], read_full=1, unread_by_source=["ats"]))
    assert "Read in full: 1" in md


def test_bad_shapes_do_not_crash_or_mark_unsent_jobs(repo):
    # review, 29 Sep 2026: also_found as strings crashed after state/seen.json was written
    seen_before = len(json.load(open(repo / "state/seen.json")))
    r, md = render(repo, dict(BASE, jobs=[dict(JOB, priority="9", fit="8.0")],
                              also_found=["Some Co, ML Engineer"], direct_look="x", rejected=["junk"]))
    assert "1 jobs rendered" in r.stderr
    assert len(json.load(open(repo / "state/seen.json"))) == seen_before + 1


def test_float_priority_does_not_break_reindex(repo):
    render(repo, dict(BASE, jobs=[dict(JOB, priority=7.5)]))
    render(repo, dict(BASE, slot="evening", jobs=[dict(JOB, title="Other ZZ", apply_url="https://example.org/j/9", priority=6)]))
    idx = json.load(open(repo / "jobs" / "index.json"))
    assert len(idx) == 2


# 29 Sep 2026: a shortlist whose date or slot differs from the run's run_slot.json is refused.
def _slot_case(tmp_path, rec, sl):
    import write_pack as W
    if rec is not None:
        (tmp_path / "run_slot.json").write_text(json.dumps(rec))
    p = tmp_path / "shortlist.json"
    p.write_text(json.dumps(sl))
    return W.slot_problem(sl, str(p))


def test_slot_matching_the_run_passes(tmp_path):
    assert _slot_case(tmp_path, {"date": "2026-09-30", "slot": "noon"},
                      {"date": "2026-09-30", "slot": "noon"}) is None


def test_noon_run_calling_itself_morning_is_refused(tmp_path):
    msg = _slot_case(tmp_path, {"date": "2026-09-30", "slot": "noon"},
                     {"date": "2026-09-30", "slot": "morning"})
    assert msg.startswith("REFUSED") and "noon" in msg


def test_wrong_date_is_refused(tmp_path):
    assert _slot_case(tmp_path, {"date": "2026-09-30", "slot": "evening"},
                      {"date": "2026-09-29", "slot": "evening"})


def test_backfill_without_run_slot_is_not_checked(tmp_path):
    assert _slot_case(tmp_path, None, {"date": "2026-09-29", "slot": "backfill"}) is None


# 30 Sep 2026: fresh jobs in his field that the run did not read are listed in the email.
def test_fresh_unread_jobs_are_listed_in_the_email(repo):
    (repo / "candidates.json").write_text(json.dumps([
        dict(company="Brainlab", title="Applied AI Engineer", date="2026-09-29", url="https://brainlab.example/1"),
        dict(company="Testfirma GmbH", title=JOB["title"], date="2026-09-29", url=JOB["apply_url"]),
        dict(company="Old Co", title="AI Engineer", date="2026-09-01", url="https://old.example/1")]))
    r, md = render(repo, dict(BASE, jobs=[JOB]))
    assert "## Fresh, not read yet (1)" in md
    assert "Brainlab | Applied AI Engineer · https://brainlab.example/1" in md
    assert "Old Co" not in md.split("## Fresh, not read yet")[1].split("##")[0]
    assert "FRESH NOT READ: 1" in r.stderr


def test_no_fresh_section_when_everything_fresh_was_read(repo):
    (repo / "candidates.json").write_text(json.dumps([
        dict(company="Testfirma GmbH", title=JOB["title"], date="2026-09-29", url=JOB["apply_url"])]))
    _, md = render(repo, dict(BASE, jobs=[JOB]))
    assert "Fresh, not read yet" not in md


# 30 Sep 2026: borderline jobs and rejections with no valid gate are listed for him to decide.
def test_borderline_and_gateless_rejections_are_listed(repo):
    (repo / "candidates.json").write_text(json.dumps([
        dict(company="Clera", title="ML Engineer", date="2026-09-20", url="https://clera.example/1")]))
    sl = dict(BASE, jobs=[JOB],
              rejected=[dict(company="Exxeta", title="AI Engineer", fit=3, gate="german", reason="Drop band: 'fließend Deutsch'"),
                        dict(company="Clera", title="ML Engineer", fit=5, reason="feels junior")],
              borderline=[dict(company="STARK", title="CV Engineer", fit=5, url="https://stark.example/1",
                               reason="asks 7 years, he has 6")])
    _, md = render(repo, sl)
    section = md.split("## Borderline, not sent (2)")[1].split("\n## ")[0]
    assert "STARK | CV Engineer · fit 5 · asks 7 years, he has 6 · https://stark.example/1" in section
    assert "Clera | ML Engineer · fit 5 · feels junior · https://clera.example/1" in section
    assert "Exxeta" not in section


# 30 Sep 2026: the run time is read off the clock from run_slot.json, never taken from the agent.
def test_elapsed_minutes_from_run_slot(tmp_path):
    import datetime
    from slots import elapsed_minutes
    start = datetime.datetime(2026, 9, 30, 8, 18, tzinfo=datetime.timezone.utc)
    (tmp_path / "run_slot.json").write_text(json.dumps({"date": "2026-09-30", "slot": "morning",
                                                        "started": start.isoformat()}))
    assert elapsed_minutes(str(tmp_path), now=start + datetime.timedelta(minutes=22, seconds=40)) == 22


def test_elapsed_minutes_unknown_without_start(tmp_path):
    from slots import elapsed_minutes
    assert elapsed_minutes(str(tmp_path)) is None
    (tmp_path / "run_slot.json").write_text(json.dumps({"date": "2026-09-30", "slot": "morning"}))
    assert elapsed_minutes(str(tmp_path)) is None


def test_render_replaces_hand_written_minutes(repo):
    import datetime
    start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=22)
    (repo / "run_slot.json").write_text(json.dumps({"date": BASE["date"], "slot": BASE["slot"],
                                                    "started": start.isoformat()}))
    _, md = render(repo, dict(BASE, jobs=[JOB], read_full=10, minutes=72))
    assert "Run time: about 72 minutes" not in md
    assert "Run time: about 22 minutes" in md or "Run time: about 23 minutes" in md
