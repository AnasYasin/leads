"""Fresh jobs in his field are read first and none is left unread (30 Sep 2026)."""
import datetime
import json

import fresh_check as F
import prescore

TODAY = datetime.date(2026, 9, 29)


def row(co, ti, date="", **kw):
    return dict(company=co, title=ti, date=date, url="https://%s.example/1" % co.lower(), source="ATS/x", **kw)


def test_a_job_posted_today_is_read_before_an_older_better_title():
    old = row("Old", "Computer Vision Engineer", "2026-09-10", desc="pytorch opencv yolo segmentation transformer onnx")
    new = row("New", "Data Scientist", "2026-09-29", desc="python and sql")
    out = prescore.order([old, new], today=TODAY)
    assert old["prescore"] > new["prescore"]                     # the title and text still score higher
    assert [j["company"] for j in out] == ["New", "Old"]          # but the fresh one is read first


def test_groups_are_one_day_three_days_then_the_rest_and_undated_last():
    rows = [row("D", "ML Engineer", "2026-09-20"), row("U", "ML Engineer"),
            row("B", "ML Engineer", "2026-09-27"), row("A", "ML Engineer", "2026-09-28")]
    assert [j["company"] for j in prescore.order(rows, today=TODAY)] == ["A", "B", "D", "U"]


def test_inside_a_group_the_prescore_decides():
    rows = [row("Low", "Data Scientist", "2026-09-29"), row("High", "Computer Vision Engineer", "2026-09-29")]
    assert [j["company"] for j in prescore.order(rows, today=TODAY)] == ["High", "Low"]


def sc_with(tmp_path, cands):
    (tmp_path / "candidates.json").write_text(json.dumps(cands))
    return str(tmp_path)


SL = dict(date="2026-09-29", slot="evening")


def test_fresh_unread_jobs_are_listed_freshest_first(tmp_path):
    sc = sc_with(tmp_path, [row("Brainlab", "Applied AI Engineer", "2026-09-29", prescore=5),
                            row("statworx", "ML Engineer", "2026-09-29", prescore=7),
                            row("Mid", "AI Engineer", "2026-09-27", prescore=9),
                            row("Old", "AI Engineer", "2026-09-20", prescore=9),
                            row("Undated", "AI Engineer", prescore=9)])
    left = F.unread_fresh(sc, SL)
    assert [c["company"] for c in left] == ["statworx", "Brainlab", "Mid"]


def test_sent_and_rejected_jobs_count_as_read_even_without_a_link(tmp_path):
    sc = sc_with(tmp_path, [row("Brainlab", "Applied AI Engineer", "2026-09-29"),
                            row("statworx", "ML Engineer", "2026-09-29"),
                            row("Apheris", "Senior ML Engineer", "2026-09-28")])
    sl = dict(SL, jobs=[dict(company="Brainlab", title="Applied AI Engineer", apply_url="https://brainlab.example/1")],
              rejected=[dict(company="statworx", title="ML Engineer", reason="fit 5")])
    assert [c["company"] for c in F.unread_fresh(sc, sl)] == ["Apheris"]


def test_the_command_fails_while_fresh_jobs_are_unread(tmp_path):
    import subprocess
    import sys
    from conftest import SCRIPTS
    sc_with(tmp_path, [row("Brainlab", "Applied AI Engineer", "2026-09-29")])
    p = tmp_path / "shortlist.json"
    p.write_text(json.dumps(SL))
    r = subprocess.run([sys.executable, SCRIPTS + "/fresh_check.py", str(p)], capture_output=True, text=True)
    assert r.returncode == 1 and "UNREAD FRESH" in r.stdout and "Brainlab" in r.stdout
    p.write_text(json.dumps(dict(SL, rejected=[dict(company="Brainlab", title="Applied AI Engineer")])))
    r = subprocess.run([sys.executable, SCRIPTS + "/fresh_check.py", str(p)], capture_output=True, text=True)
    assert r.returncode == 0
