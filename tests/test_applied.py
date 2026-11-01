"""applied.py stamps or adds the applications.md row and the store then shows the job as applied."""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import applied  # noqa: E402
import pipeline  # noqa: E402
import store  # noqa: E402
from test_store import PACK  # noqa: E402

LOG = """# Applications log

| Researched | Company | Role | Location | Verdict | Docs built | Applied | Outcome |
|---|---|---|---|---|---|---|---|
| 2026-10-30 | Testfirma GmbH | Computer Vision Engineer (m/w/d) | Berlin | fit 8 | CV | no | |
"""


def test_an_existing_row_is_stamped_and_a_new_one_added(tmp_path, monkeypatch, capsys):
    p = tmp_path / "state/applications.md"
    p.write_text(LOG, encoding="utf-8")
    monkeypatch.setattr(pipeline, "APPS", Path(p))
    assert applied.main(["Testfirma GmbH", "Computer Vision Engineer", "--cv", "CV_LLM", "--date", "2026-11-01", "--no-push"]) == 0
    assert applied.main(["Other AG", "ML Engineer", "--date", "2026-11-01", "--no-push"]) == 0
    assert applied.main(["Other AG", "ML Engineer", "--date", "2026-11-02", "--no-push"]) == 1       # already applied
    t = p.read_text(encoding="utf-8")
    assert "| Testfirma GmbH | Computer Vision Engineer (m/w/d) | Berlin | fit 8 | CV_LLM | yes 2026-11-01 (by hand) |" in t
    assert "| 2026-11-01 | Other AG | ML Engineer |  | applied by hand |  | yes 2026-11-01 (by hand) |" in t
    assert "already says applied" in capsys.readouterr().out


def test_the_store_shows_the_hand_marked_job_as_applied(tmp_path, monkeypatch):
    (tmp_path / "jobs").mkdir(exist_ok=True)
    (tmp_path / "jobs/testfirma-computer-vision-engineer-berlin.md").write_text(PACK, encoding="utf-8")
    p = tmp_path / "state/applications.md"
    p.write_text(LOG, encoding="utf-8")
    monkeypatch.setattr(pipeline, "APPS", Path(p))
    applied.main(["Testfirma GmbH", "Computer Vision Engineer", "--cv", "CV", "--date", "2026-11-01", "--no-push"])
    path, _ = store.build(str(tmp_path))
    db = sqlite3.connect(path)
    assert db.execute("SELECT applied_on, applied_cv FROM jobs").fetchone() == ("yes 2026-11-01 (by hand)", "CV")
    assert db.execute("SELECT COUNT(*) FROM open_jobs").fetchone()[0] == 0
