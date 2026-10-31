"""The reader, the verdicts and the decision memory (docs/PROBLEMS.md group 2, and 4.1, 4.2, 5.1; 2 Oct 2026).

A job counts as read only when scripts/read_next.py printed all of it. A verdict is handed in before
the next batch. write_pack.py and final_check.py take what was read from the reader's log, and
state/decisions.json keeps every verdict so a later run does not read the job again."""
import datetime
import json
import subprocess
import sys
import os

import pytest

import decisions as D
import final_check as F
import read_next as R
import verdict as V
from conftest import SCRIPTS

WORK = ("You train and ship PyTorch models for computer vision and you own the evaluation and the data pipeline. "
        "The team is twelve engineers in Berlin and the product runs in forty hospitals. ")


def row(n, tail="Our working language is English.", **kw):
    r = dict(id="acme%d-ml-engineer" % n, company="Acme%d" % n, title="ML Engineer", location="Berlin", url="https://acme%d.example/job" % n,
             source="ATS/ats:ashby", date="2026-10-02", prescore=5, desc=(WORK * 6) + tail)
    r.update(kw)
    return r


@pytest.fixture
def sc(tmp_path):
    def make(rows, started_minutes_ago=5):
        started = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=started_minutes_ago)
        (tmp_path / "candidates.json").write_text(json.dumps(rows))
        (tmp_path / "run_slot.json").write_text(json.dumps({"date": "2026-10-02", "slot": "evening", "started": started.isoformat()}))
        return str(tmp_path)
    return make


def verdict(i, fit=7, gate="", band="A", lang="Our working language is English.", reason="Detection and deployment, his Civixa and SPHF work.",
            hard_req="none"):
    return dict(id=i, fit=fit, gate=gate, band=band, lang_line=lang, reason=reason, hard_req=hard_req)


def hand_in(sc, rows, argv=("verdict.py", "x", "v.json", "--no-next")):
    p = os.path.join(sc, "v.json")
    json.dump(rows, open(p, "w"))
    old, sys.argv = sys.argv, list(argv)
    try:
        return V.hand_in(sc, p)
    finally:
        sys.argv = old


# --- the reader --------------------------------------------------------------------------------

def test_a_batch_is_printed_whole_and_logged(sc, capsys):
    s = sc([row(1), row(2, tail="Last line of the second posting."), row(3)])
    assert R.main(["x", s]) == 0
    out = capsys.readouterr().out
    for r in R.candidates(s):
        assert r["desc"] in out                               # every character of every job
    assert "Last line of the second posting." in out and "KEY LINES" in out
    assert set(R.log(s)["printed"]) == {"acme1-ml-engineer", "acme2-ml-engineer", "acme3-ml-engineer"}
    assert open(os.path.join(s, "batches", "batch_1.txt")).read().strip() in out


def test_a_batch_stays_under_the_size_limit(sc, capsys):
    s = sc([row(i, desc=WORK * 40) for i in range(1, 6)])      # about 7,800 characters each
    R.main(["x", s])
    assert len(R.log(s)["printed"]) == 2 and len(capsys.readouterr().out) < 26000


def test_no_new_batch_before_the_verdicts(sc, capsys):
    s = sc([row(i, desc=WORK * 40) for i in range(1, 6)])
    R.main(["x", s])
    capsys.readouterr()
    assert R.main(["x", s]) == 1 and "NO NEW BATCH" in capsys.readouterr().out
    assert hand_in(s, [verdict(i) for i in R.pending(s)]) == 0
    assert R.main(["x", s]) == 0 and len(R.log(s)["printed"]) == 4


def test_a_job_without_text_is_never_printed_or_counted(sc, capsys):
    s = sc([row(1), row(2, desc=""), row(3, desc="Siehe Homepage.")])
    R.main(["x", s])
    out = capsys.readouterr().out
    assert "2 without text" in out and list(R.log(s)["printed"]) == ["acme1-ml-engineer"]
    assert hand_in(s, [verdict("acme2-ml-engineer")]) == 1           # a verdict on an unread job is refused
    hand_in(s, [verdict("acme1-ml-engineer")])
    assert V.counts(s) == dict(candidates=3, read_full=1, left_unread=2, unread_by_source={"ats": 2}, no_text=2, remembered=0)


def test_reading_stops_at_the_time_limit(sc, capsys):
    s = sc([row(1)], started_minutes_ago=81)
    assert R.main(["x", s]) == 2 and "TIME." in capsys.readouterr().out
    assert R.main(["x", s, "--more"]) == 0


def test_the_key_lines_are_pulled_out(sc, capsys):
    text = (WORK * 5) + "\nRequirements\n• 5+ years of experience in ML\n• NATO nationality is required\n• PhD is a plus\n• Fluent English, German is a plus"
    s = sc([row(1, desc=text)])
    R.main(["x", s])
    out = capsys.readouterr().out
    head = out.split("FULL TEXT")[0]
    assert "years: • 5+ years of experience in ML" in head and "clearance or nationality: • NATO nationality is required" in head
    assert "phd: • PhD is a plus" in head and "language: • Fluent English, German is a plus" in head


def test_handing_in_the_verdicts_prints_the_next_batch(sc, capsys):
    s = sc([row(i, desc=WORK * 40) for i in range(1, 6)])
    R.main(["x", s])
    capsys.readouterr()
    assert hand_in(s, [verdict(i) for i in R.pending(s)], argv=("verdict.py", s, "-")) == 0
    out = capsys.readouterr().out
    assert "The batch is complete." in out and "[3 of 5]" in out and len(R.log(s)["printed"]) == 4


# --- the verdicts ------------------------------------------------------------------------------

def test_fit_and_gate_decide_where_a_job_goes(sc):
    s = sc([row(1), row(2), row(3), row(4), row(5, referral=True)])
    R.main(["x", s])
    assert hand_in(s, [verdict("acme1-ml-engineer", fit=8), verdict("acme2-ml-engineer", fit=6),
                       verdict("acme3-ml-engineer", fit=5), verdict("acme4-ml-engineer", fit=7, gate="years", reason="Requires 10+ years of experience."),
                       verdict("acme5-ml-engineer", fit=5)]) == 0
    got = {i: v["verdict"] for i, v in R.verdicts(s).items()}
    assert got == {"acme1-ml-engineer": "send", "acme2-ml-engineer": "also", "acme3-ml-engineer": "borderline",
                   "acme4-ml-engineer": "reject", "acme5-ml-engineer": "send"}
    built = V.lists(s)
    assert [j["company"] for j in built["jobs"]] == ["Acme1", "Acme5"] and built["jobs"][0]["desc"].endswith("English.")
    assert built["rejected"][0]["gate"] == "years" and built["also_found"][0]["fit"] == 6


@pytest.mark.parametrize("bad, why", [
    (dict(gate="python"), "is not one of"),                                   # software skills are never a gate
    (dict(lang="no language line in the posting"), "names German"),         # the text has a German line
    (dict(reason="ok"), "reason is missing"),
    (dict(band=""), "band must be A or B"),
    (dict(fit="high"), "fit must be a number"),
])
def test_a_careless_verdict_is_refused(sc, capsys, bad, why):
    s = sc([row(1, tail="German is a plus, English is the working language.")])
    R.main(["x", s])
    capsys.readouterr()
    v = verdict("acme1-ml-engineer", lang="German is a plus, English is the working language.")
    v.update({"lang_line" if k == "lang" else k: x for k, x in bad.items()})
    assert hand_in(s, [v]) == 1 and why in capsys.readouterr().out and not R.verdicts(s)


def test_a_certain_german_line_cannot_be_waved_through(sc, capsys):
    s = sc([row(1, tail="Fluent German is required.", referral=True), row(2, tail="Fluent German is required.")])
    R.main(["x", s])
    capsys.readouterr()
    assert hand_in(s, [verdict("acme2-ml-engineer", lang="Fluent German is required.")]) == 1
    assert "Reject it with gate german" in capsys.readouterr().out
    assert hand_in(s, [verdict("acme2-ml-engineer", fit=7, gate="german", lang="Fluent German is required.", reason="Drop band, the posting asks for fluent German."),
                       verdict("acme1-ml-engineer", fit=6, lang="Fluent German is required.", band="B")]) == 0     # referral rows are exempt


def test_an_unclear_german_line_must_be_quoted(sc, capsys):
    s = sc([row(1, tail="Please note that for this role a C2 proficiency in German, Italian or French is required.")])
    R.main(["x", s])
    assert "GERMAN LINE TO DECIDE" in capsys.readouterr().out
    assert hand_in(s, [verdict("acme1-ml-engineer", lang="Our team speaks English")]) == 1
    assert hand_in(s, [verdict("acme1-ml-engineer", band="B", lang="C2 proficiency in German, Italian or French is required")]) == 0


# --- nothing unread is sent --------------------------------------------------------------------

def shortlist(sc, jobs):
    p = os.path.join(sc, "shortlist.json")
    json.dump(dict(date="2026-10-02", slot="evening", jobs=jobs), open(p, "w"))
    return p


def test_final_check_refuses_a_job_nobody_read(sc, tmp_path):
    s = sc([row(1), row(2), row(3, desc="")])
    R.main(["x", s])
    hand_in(s, [verdict("acme1-ml-engineer", fit=8), verdict("acme2-ml-engineer", fit=6)])
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    (root / "state/seen.json").write_text("[]")
    (root / "state/applications.md").write_text("")
    jobs = [dict(company="Acme1", title="ML Engineer", apply_url="https://acme1.example/job", desc=row(1)["desc"]),
            dict(company="Acme2", title="ML Engineer", apply_url="https://acme2.example/job", desc=row(2)["desc"]),
            dict(company="Acme3", title="ML Engineer", apply_url="https://acme3.example/job", desc=""),
            dict(company="Elsewhere", title="CV Engineer", apply_url="https://else.example/job", desc=WORK * 6)]
    got = {r[1]: (r[0], r[3]) for r in F.check(shortlist(s, jobs), root=str(root))}
    assert got["Acme1"][0] == "OK"
    assert got["Acme2"][0] == "UNREAD" and "'also'" in got["Acme2"][1]
    assert got["Acme3"][0] == "UNREAD" and "no text" in got["Acme3"][1]
    assert got["Elsewhere"][0] == "UNREAD" and "--add" in got["Elsewhere"][1]


def test_write_pack_refuses_an_unread_job(sc):
    s = sc([row(1), row(2)])
    R.main(["x", s])
    hand_in(s, [verdict("acme1-ml-engineer", fit=8)])
    p = shortlist(s, [dict(company="Acme2", title="ML Engineer", apply_url="https://acme2.example/job", desc=row(2)["desc"])])
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "write_pack.py"), p], capture_output=True, text=True)
    assert r.returncode != 0 and "REFUSED" in r.stderr and "it has no verdict" in r.stderr


def test_the_draft_lists_only_what_was_read(sc, capsys):
    s = sc([row(1), row(2), row(3, desc="")])
    R.main(["x", s])
    hand_in(s, [verdict("acme1-ml-engineer", fit=8), verdict("acme2-ml-engineer", fit=3, gate="field", reason="A sales role with no ML work at all.")])
    assert V.draft(s) == 0
    sl = json.load(open(os.path.join(s, "shortlist.json")))
    assert [j["id"] for j in sl["jobs"]] == ["acme1-ml-engineer"] and len(sl["rejected"]) == 1
    assert sl["read_full"] == 2 and sl["left_unread"] == 1 and sl["no_text"] == 1 and sl["date"] == "2026-10-02"


# --- the memory --------------------------------------------------------------------------------

def test_a_job_read_before_is_not_read_again(tmp_path):
    cands = [row(1), row(2)]
    D.record({"acme1-ml-engineer": dict(company="Acme1", title="ML Engineer", verdict="reject", fit=4, gate="field",
                                        band="", lang_line="", reason="Sales role.")}, cands, "2026-10-01", "evening", str(tmp_path))
    rows = D.load(str(tmp_path))
    assert len(rows) == 1 and rows[0]["print"] and rows[0]["chars"] == len(row(1)["desc"])
    kept, remembered = D.split([row(1), row(2)], rows, "2026-10-02")
    assert [j["company"] for j in kept] == ["Acme2"] and remembered[0][1]["verdict"] == "reject"
    # the same job from another board, with another footer: still the same text
    copy = row(1, url="https://www.linkedin.com/jobs/view/123", source="linkedin", desc=row(1)["desc"] + " Referrals increase your chances.")
    assert D.split([copy], rows, "2026-10-02")[1]
    # a card with no text yet is matched on the job alone
    assert D.split([row(1, desc="")], rows, "2026-10-02")[1]


def test_a_changed_text_is_read_again_and_an_old_verdict_expires(tmp_path):
    D.record({"acme1-ml-engineer": dict(company="Acme1", title="ML Engineer", verdict="also", fit=6)}, [row(1)],
             "2026-10-01", "evening", str(tmp_path))
    rows = D.load(str(tmp_path))
    rewritten = row(1, desc="We now look for a research engineer in speech recognition. " * 12 + "Whisper, wav2vec and Kaldi are daily tools.")
    kept, remembered = D.split([rewritten], rows, "2026-10-02")
    assert not remembered and "text has changed" in kept[0]["text_changed"]
    assert D.split([row(1)], rows, "2026-10-16")[0] and not D.split([row(1)], rows, "2026-10-16")[1]     # 15 days later


def test_a_wrong_verdict_can_be_forgotten(tmp_path):
    D.record({"acme1-ml-engineer": dict(company="BaehrBots", title="AI Integration Engineer", verdict="reject", fit=6, gate="german")},
             [], "2026-10-01", "evening", str(tmp_path))
    assert len(D.forget("baehrbots", "integration engineer", str(tmp_path))) == 1 and D.load(str(tmp_path)) == []


def test_filter_run_drops_remembered_jobs(tmp_path):
    sc = tmp_path / "sc"
    sc.mkdir()
    for src in ("ba", "getro", "talent", "arbeitnow", "linkedin", "xing", "stepstone"):
        (sc / (src + ".json")).write_text("[]")
    rows = [dict(company="Zz Remember Co", title="Machine Learning Engineer", location="Berlin, Germany", url="https://zz.example/1",
                 date="2099-01-01", desc=WORK * 6, source="greenhouse"),
            dict(company="Zz New Co", title="Machine Learning Engineer", location="Berlin, Germany", url="https://zz.example/2",
                 date="2099-01-01", desc=WORK * 6, source="greenhouse")]
    (sc / "ats.json").write_text(json.dumps(rows))
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    import shutil
    for f in os.listdir(SCRIPTS):
        if f.endswith(".py"):
            shutil.copy(os.path.join(SCRIPTS, f), root / "scripts" / f)
    shutil.copytree(os.path.join(os.path.dirname(SCRIPTS), "config"), root / "config")
    (root / "state/seen.json").write_text("[]")
    (root / "state/applications.md").write_text("")
    today = datetime.date.today().isoformat()
    D.record({"x": dict(company="Zz Remember Co", title="Machine Learning Engineer", verdict="reject", fit=4, gate="field", reason="no")},
             [dict(id="x", desc=WORK * 6, url="https://zz.example/1")], today, "morning", str(root))
    p = subprocess.run([sys.executable, str(root / "scripts" / "filter_run.py"), str(sc)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-2000:]
    assert [c["company"] for c in json.load(open(sc / "candidates.json"))] == ["Zz New Co"]
    assert json.load(open(sc / "remembered.json"))[0]["verdict"] == "reject" and "verdict remembered: 1 skipped" in p.stderr


def test_one_title_posted_twice_with_different_texts_keeps_both_verdicts(tmp_path):
    # Mistral "AI Scientist", typeform "Staff AI Engineer": one title, several postings, different texts.
    a = row(1, id="a", url="https://acme1.example/job/paris")
    b = row(1, id="b", url="https://acme1.example/job/berlin", desc="A research role on speech models in Berlin. " * 20)
    D.record({"a": dict(company="Acme1", title="ML Engineer", verdict="reject", fit=3, gate="field"),
              "b": dict(company="Acme1", title="ML Engineer", verdict="send", fit=8)}, [a, b], "2026-10-01", "evening", str(tmp_path))
    rows = D.load(str(tmp_path))
    assert len(rows) == 2
    kept, remembered = D.split([dict(a), dict(b)], rows, "2026-10-02")
    assert not kept and [m["verdict"] for _, m in remembered] == ["reject", "send"]


# --- 4.3 a hard requirement he cannot back caps the fit at 6 -------------------------------------------
ZOOPLUS = "3+ years of experience with LP/MIP modelling and a commercial solver such as Gurobi."


def test_a_hard_requirement_caps_the_fit_and_is_shown(sc, capsys):
    s = sc([row(1, tail=ZOOPLUS + " Our working language is English."), row(2), row(3)])
    R.main(["x", s])
    capsys.readouterr()
    v = verdict("acme1-ml-engineer", fit=8, hard_req="3+ years of experience with LP/MIP modelling and a commercial solver such as Gurobi")
    unsaid = verdict("acme2-ml-engineer", fit=8)
    del unsaid["hard_req"]
    assert hand_in(s, [v, unsaid, verdict("acme3-ml-engineer", fit=8, hard_req="10 years of Rust")]) == 1
    out = capsys.readouterr().out
    assert "Say hard_req" in out and "must quote the requirement from the text" in out
    got = R.verdicts(s)
    assert list(got) == ["acme1-ml-engineer"] and got["acme1-ml-engineer"]["fit"] == 6 and got["acme1-ml-engineer"]["verdict"] == "also"
    line = V.lists(s)["also_found"][0]
    assert line["note"].startswith("NEEDS: '3+ years of experience with LP/MIP") and line["fit"] == 6


def test_a_hard_requirement_is_not_a_gate_and_a_referral_is_still_sent(sc):
    s = sc([row(1, tail=ZOOPLUS + " Our working language is English.", referral=True)])
    R.main(["x", s])
    hand_in(s, [verdict("acme1-ml-engineer", fit=8, hard_req="3+ years of experience with LP/MIP modelling")])
    job = V.lists(s)["jobs"][0]
    assert job["fit"] == 6 and "Hard requirement he cannot back" in job["gaps"]
