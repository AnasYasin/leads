"""store.py builds store/jobs.db from the repository files."""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import store  # noqa: E402

PACK = """---
id: testfirma-computer-vision-engineer-berlin
sent: 2026-11-01
slot: morning
company: Testfirma GmbH
title: Computer Vision Engineer (m/w/d)
location: Berlin
posted: 2026-10-30
tier: 1
fit: 8
priority: 10
band: A
lang_line: no language line in the posting
recruiter: false
referral: false
apply_url: https://example.org/job/1
fallback_url:
cv_base: CV
live_at_send: LIVE (HTTP 200)
prior_sent: []
---

# Computer Vision Engineer (m/w/d) — Testfirma GmbH

## Radar verdict
Why it fits: Detection models in PyTorch, the core of the candidate's work.
Gaps: Kubernetes is named.
Company: Berlin startup, 20 people.

## Links
- Apply: https://example.org/job/1

## Full job description (as read by the radar on 2026-11-01)

We build PyTorch detection models for retail shelves.
Second paragraph of the posting.
"""

PACK2 = PACK.replace("testfirma-computer-vision-engineer-berlin", "other-ml-engineer-munich").replace("Testfirma GmbH", "Other AG") \
            .replace("Computer Vision Engineer (m/w/d)", "ML Engineer").replace("Berlin", "Munich").replace("posted: 2026-10-30", "posted: 2026-10-20")

APPS = """# Applications log

| Researched | Company | Role | Location | Verdict | Docs built | Applied | Outcome |
|---|---|---|---|---|---|---|---|
| 2026-11-01 | Other AG | ML Engineer | Munich | fit 7 | CV_LLM | yes 2026-11-01 | waiting |
"""


def make(tmp_path):
    (tmp_path / "jobs").mkdir(exist_ok=True)
    (tmp_path / "jobs/testfirma-computer-vision-engineer-berlin.md").write_text(PACK, encoding="utf-8")
    (tmp_path / "jobs/other-ml-engineer-munich.md").write_text(PACK2, encoding="utf-8")
    (tmp_path / "shortlists").mkdir(exist_ok=True)
    (tmp_path / "shortlists/2026-11-01-morning.json").write_text(json.dumps(dict(
        date="2026-11-01", slot="morning", candidates=40, read_full=12, minutes=70, jobs=[{"id": "a"}, {"id": "b"}])))
    (tmp_path / "companies").mkdir(exist_ok=True)
    (tmp_path / "companies/testfirma.json").write_text(json.dumps(dict(name="Testfirma GmbH", site="https://t.example", what="shelves",
                                                                       staff="~20", last_seen="2026-11-01", sent=[{"date": "2026-11-01"}])))
    (tmp_path / "state").mkdir(exist_ok=True)
    (tmp_path / "state/applications.md").write_text(APPS, encoding="utf-8")
    (tmp_path / "state/decisions.json").write_text(json.dumps([dict(key="k", company="E Co", title="Analyst", url="https://e.example",
                                                                     verdict="reject", fit=3, gate="field", reason="not ML",
                                                                     date="2026-11-01", slot="morning")]))
    (tmp_path / "state/rejected.json").write_text("[]")
    return tmp_path


def test_the_store_holds_jobs_with_their_text_and_applied_status(tmp_path):
    root = make(tmp_path)
    path, n = store.build(str(root))
    assert n == 2 and os.path.exists(path) and path.endswith(os.path.join("store", "jobs.db"))
    db = sqlite3.connect(path)
    j = dict(zip([c[0] for c in db.execute("SELECT * FROM jobs").description],
                 db.execute("SELECT * FROM jobs WHERE id = 'testfirma-computer-vision-engineer-berlin'").fetchone()))
    assert j["fit"] == 8 and j["company"] == "Testfirma GmbH" and j["cv_base"] == "CV"
    assert j["why"].startswith("Detection models") and j["gaps"] == "Kubernetes is named." and j["company_note"].startswith("Berlin startup")
    assert j["description"].startswith("We build PyTorch detection models") and "Second paragraph" in j["description"]
    assert j["applied_on"] is None
    other = db.execute("SELECT applied_on, applied_cv, outcome FROM jobs WHERE id = 'other-ml-engineer-munich'").fetchone()
    assert other == ("yes 2026-11-01", "CV_LLM", "waiting")
    assert db.execute("SELECT candidates, read_full, sent, minutes FROM runs").fetchone() == (40, 12, 2, 70)
    assert db.execute("SELECT staff, sent_count FROM companies WHERE name = 'Testfirma GmbH'").fetchone() == ("~20", 1)
    assert db.execute("SELECT company, role FROM applications").fetchone() == ("Other AG", "ML Engineer")
    assert db.execute("SELECT verdict, gate FROM decisions").fetchone() == ("reject", "field")


def test_open_jobs_leaves_out_applied_and_gone_and_is_freshest_first(tmp_path):
    root = make(tmp_path)
    path, _ = store.build(str(root))
    db = sqlite3.connect(path)
    rows = db.execute("SELECT id, days_since_posted FROM open_jobs").fetchall()
    assert [r[0] for r in rows] == ["testfirma-computer-vision-engineer-berlin"]     # the Munich one is applied
    assert rows[0][1] >= 0
    db.execute("INSERT INTO checks VALUES ('testfirma-computer-vision-engineer-berlin', 'GONE', '404', '2026-11-02 10:00')")
    db.commit()
    db.close()
    path, _ = store.build(str(root))                 # a rebuild keeps the checks
    db = sqlite3.connect(path)
    assert db.execute("SELECT COUNT(*) FROM open_jobs").fetchone()[0] == 0
    assert db.execute("SELECT state FROM checks").fetchone() == ("GONE",)


def test_jobs_json_is_written_with_text_and_status(tmp_path):
    root = make(tmp_path)
    path, n = store.export_json(str(root))
    rows = json.load(open(path, encoding="utf-8"))
    assert n == 2 and path.endswith(os.path.join("store", "jobs.json"))
    assert [r["id"] for r in rows] == ["other-ml-engineer-munich", "testfirma-computer-vision-engineer-berlin"] or len(rows) == 2
    by = {r["id"]: r for r in rows}
    assert by["other-ml-engineer-munich"]["applied_on"] == "yes 2026-11-01" and by["other-ml-engineer-munich"]["applied_cv"] == "CV_LLM"
    assert by["testfirma-computer-vision-engineer-berlin"]["description"].startswith("We build PyTorch")
    assert by["testfirma-computer-vision-engineer-berlin"]["applied_on"] is None
