"""docs/PROBLEMS.md groups 4 to 8, the parts fixed on 2 Oct 2026. Each test names the problem it pins down."""
import json

import decisions as D
import fetch_desc as FD
import jobid
import leftover as L
import rejected as RJ
import salary
import send_mail as SM
import write_pack as W

WORK = ("You train and ship PyTorch models for computer vision and you own the evaluation and the data pipeline. "
        "The team is twelve engineers in Berlin and the product runs in forty hospitals. ")


# --- 5.3 the same job, the same link, sent four times -------------------------------------------------
QS = "https://career.quantum-systems.com/o/senior-robotics-machine-learning-engineer-mfd"
SEEN = [dict(id="quantum-systems-machine-learning-engineer-gilching", company="Quantum-Systems", location="Gilching",
             title="Senior Machine Learning Engineer (m/f/d)", sent="2026-08-01",
             url="https://career.quantum-systems.com/o/senior-machine-learning-engineer-mfd-1"),
        dict(id="quantum-systems-robotics-machine-learning-engineer-munchen", company="Quantum-Systems", location="München",
             title="Senior Robotics & Machine Learning Engineer (m/f/d)", sent="2026-09-29", url=QS)]


def test_a_job_matches_its_own_entry_before_an_older_lookalike():
    title = "Senior Robotics & Machine Learning Engineer (m/f/d)"
    pool = {jobid.norm_url(QS), jobid.norm_url(SEEN[0]["url"])}
    m = jobid.is_repeat("Quantum-Systems", title, "München, DE", SEEN, QS)
    assert m["sent"] == "2026-09-29" and not jobid.second_opening(QS, title, m, pool)          # a repeat
    # before its first send it was a real second opening beside the 1 Aug job, and still is
    m = jobid.is_repeat("Quantum-Systems", title, "München, DE", SEEN[:1], QS)
    assert m["sent"] == "2026-08-01" and jobid.second_opening(QS, title, m, pool)


# --- 5.2 the same job under another company name ------------------------------------------------------
def repo(tmp_path, packs):
    root = tmp_path / "repo"
    (root / "jobs").mkdir(parents=True, exist_ok=True)
    seen = []
    for i, (co, ti, text, sent) in enumerate(packs):
        rel = "jobs/p%d.md" % i
        (root / rel).write_text("---\ncompany: %s\ntitle: %s\n---\n\n## Full job description (as read by the radar)\n\n%s\n" % (co, ti, text))
        seen.append(dict(id="p%d" % i, company=co, title=ti, sent=sent, url="https://x.example/%d" % i, pack=rel))
    (root / "state/seen.json").write_text(json.dumps(seen))
    return root


def test_the_same_text_under_another_company_name_is_a_repeat(tmp_path):
    text = WORK * 5 + "You will build perception models for automated driving."
    root = repo(tmp_path, [("ARRK Engineering GmbH", "Machine Learning Engineer Automatisiertes Fahren (m/w/d)", text, "2026-09-06")])
    prints = D.sent_prints(str(root), "2026-10-02")
    twin = D.text_twin("Machine Learning Engineer Automatisiertes Fahren (m/w/d)", text + " Find more jobs here.", prints)
    assert twin and twin["company"] == "ARRK Engineering GmbH"
    assert D.text_twin("Machine Learning Engineer Automatisiertes Fahren", "A different posting about speech models. " * 20, prints) is None
    assert D.text_twin("Sales Manager", text, prints) is None                    # the same text needs the same title too
    assert D.sent_prints(str(root), "2026-12-31") == []                         # sends older than 60 days are not compared


def test_a_card_row_is_checked_for_repeats_once_its_text_is_fetched(tmp_path, monkeypatch):
    # HUK-COBURG, sent 14 Sep, came back on LinkedIn as "Mecklenburgische Versicherungs-Gesellschaft".
    text = "HUK-COBURG Versicherungsgruppe\n(Senior) Applied Scientist (Machine Learning) (w/m/d)\nCoburg\n" + WORK * 4
    seen = [dict(id="huk", company="HUK-COBURG", title="(Senior) Applied Scientist (Machine Learning) (w/m/d)",
                 location="Coburg", sent="2026-09-14", url="https://www.huk.de/karriere.html")]
    monkeypatch.setattr(FD, "_repeat_data", lambda sc: (seen, set(), []))
    rows = [dict(company="Mecklenburgische Versicherungs-Gesellschaft a. G.", title="(Senior) Applied Scientist (Machine Learning) (w/m/d)",
                 location="Coburg, Bavaria, Germany", source="linkedin", url="https://de.linkedin.com/jobs/view/1", li_id="1"),
            dict(company="Other Co", title="ML Engineer", location="Berlin", source="linkedin", url="https://de.linkedin.com/jobs/view/2", li_id="2")]
    (tmp_path / "candidates.json").write_text(json.dumps(rows))
    s = FD.run(str(tmp_path), {"linkedin": lambda j: dict(j, desc=text if j["li_id"] == "1" else WORK * 5)})
    assert s["repeats"] == 1 and [c["company"] for c in json.load(open(tmp_path / "candidates.json"))] == ["Other Co"]
    assert "HUK-COBURG" in json.load(open(tmp_path / "repeats_after_fetch.json"))[0]["matched"]


# --- 5.4 a row without text is not "read" -------------------------------------------------------------
def test_an_unread_row_stays_in_the_backlog_even_when_a_similar_job_was_read(tmp_path):
    root, sc = tmp_path / "repo", tmp_path / "sc"
    root.mkdir(exist_ok=True), sc.mkdir()
    (root / "state/seen.json").write_text("[]")
    (root / "state/applications.md").write_text("")
    rows = [dict(id="revolut-data-scientist-credit", company="Revolut", title="Data Scientist (Credit)", url="https://r.example/1", source="getro:x", desc=""),
            dict(id="revolut-data-scientist-risk", company="Revolut", title="Data Scientist (Risk)", url="https://r.example/2", source="getro:x", desc=WORK * 5)]
    (sc / "candidates.json").write_text(json.dumps(rows))
    (sc / "run_slot.json").write_text(json.dumps({"date": "2026-10-02", "slot": "evening"}))
    (sc / "verdicts.json").write_text(json.dumps({"revolut-data-scientist-risk": dict(verdict="reject")}))
    sl = dict(date="2026-10-02", slot="evening", rejected=[dict(company="Revolut", title="Data Scientist (Risk)")])
    L.after_render(str(sc), sl, str(root))
    assert [e["title"] for e in L.load(str(root))] == ["Data Scientist (Credit)"]


# --- 5.5 and 6.1 the email ----------------------------------------------------------------------------
def test_an_empty_noon_run_is_not_mailed(tmp_path):
    md = tmp_path / "2026-10-01-noon.md"
    md.write_text("# Job radar, 2026-10-01 noon, 0 new\n")
    (tmp_path / "2026-10-01-noon.json").write_text(json.dumps(dict(slot="noon", jobs=[], also_found=[], borderline=[])))
    assert SM.empty_noon(md)
    (tmp_path / "2026-10-01-noon.json").write_text(json.dumps(dict(slot="noon", jobs=[], also_found=[dict(company="A")])))
    assert not SM.empty_noon(md)
    (tmp_path / "2026-10-01-evening.json").write_text(json.dumps(dict(slot="evening", jobs=[])))
    assert not SM.empty_noon(tmp_path / "2026-10-01-evening.md")           # morning and evening always report


def test_the_email_stops_before_the_run_details():
    import re
    import deliver
    rx = deliver.CUT.pattern            # the one cut rule, shared by the issue and the email (1 Nov 2026)
    body = "# Job radar\n\n1. **A job**\n\nRead in full: 40 of 45.\n\n## Run details\n\n### Source coverage\n\n## Rejected\n\n- x"
    assert re.split(rx, body, flags=re.M | re.I)[0].rstrip().endswith("Read in full: 40 of 45.")
    old = "# Job radar\n\n1. **A job**\n\n## Source coverage\n\n## Rejected\n\n- x"
    assert "Source coverage" in re.split(rx, old, flags=re.M | re.I)[0] and "- x" not in re.split(rx, old, flags=re.M | re.I)[0]


# --- 6.3 relisted dates, 6.4 job board links ----------------------------------------------------------
def test_a_relisted_job_says_so():
    assert "RELISTED" in W.date_remark(dict(posted="2026-05-13", posted_listing="2026-10-02", source="linkedin"))
    assert "RELISTED" not in W.date_remark(dict(posted="2026-09-30", posted_listing="2026-10-02", source="linkedin"))
    assert "employer's own date was not found" in W.date_remark(dict(posted="2026-10-02", source="linkedin"))
    assert W.date_remark(dict(posted="2026-10-02", source="ATS/ats:ashby")) == ""


def test_a_job_board_link_is_named_as_one():
    assert W.on_job_board("https://de.linkedin.com/jobs/view/123") and W.on_job_board("https://www.stepstone.de/stellenangebote--x")
    assert not W.on_job_board("https://jobs.ashbyhq.com/acme/1") and not W.on_job_board("https://career.acme.com/o/ml") and not W.on_job_board("")
    block = W.job_block(1, dict(title="T", company="C", apply_url="https://www.xing.com/jobs/x", fit=7, priority=8), "jobs/x.md")
    assert "a job board copy" in block


# --- 6.5 the gate is stored ---------------------------------------------------------------------------
def test_the_gate_is_stored_and_read_back():
    rows = []
    RJ.merge(rows, [dict(company="Acme", title="ML Engineer", fit=6, gate="german", reason="Drop band: 'Sehr gute Deutschkenntnisse (C1)'")], "2026-10-02")
    assert rows[0]["gate"] == "german"
    m = RJ.LINE.match("- ML Engineer — Acme · fit 6 · gate german · Drop band: 'Sehr gute Deutschkenntnisse (C1)'")
    assert m.group("gate") == "german" and m.group("reason").startswith("Drop band")
    assert RJ.LINE.match("- ML Engineer — Acme · fit 6 · Drop band").group("reason") == "Drop band"       # the old line shape


# --- 4.6 headcount, and the priority sum --------------------------------------------------------------
def test_the_ask_line_says_where_the_headcount_comes_from(monkeypatch):
    monkeypatch.setattr(salary, "ASK", dict(salary.ASK, large=("EUR 65-75k", "your rule for a large corporation, 1,000+ staff")))
    base = dict(title="T", company="C", apply_url="https://c.example/1", fit=7, priority=8, size_class="large", staff="~1,600")
    assert "headcount NOT CHECKED" in W.job_block(1, dict(base), "p")
    assert "headcount from their LinkedIn page" in W.job_block(1, dict(base, staff_source="their LinkedIn page"), "p")


def test_freshness_counts_no_date_as_minus_two():
    assert W.freshness("", "2026-10-02") == -2 and W.freshness("2026-10-02", "2026-10-02") == 2 and W.freshness("2026-09-01", "2026-10-02") == -2
