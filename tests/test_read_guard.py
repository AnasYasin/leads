"""A real run cannot render without the reader, and every run leaves a reading record (3 Oct 2026).

Until 2 Oct "read in full" was a number the run typed into shortlist.json and nothing checked it.
The reader log closed that, but a render with no log at all was still let through unchecked, which
was meant for laptop backfills. A real run has run_slot.json, so the two can be told apart."""
import json
import os
import subprocess
import sys

import final_check as F
import read_audit as A
import read_next as R
import verdict as V
from conftest import SCRIPTS
from test_reading import hand_in, row, sc, shortlist, verdict  # noqa: F401  (sc is a fixture)

JOB1 = dict(company="Acme1", title="ML Engineer", apply_url="https://acme1.example/job", desc=row(1)["desc"])


def render(path):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "write_pack.py"), path], capture_output=True, text=True)


def test_a_real_run_that_never_started_the_reader_is_refused(sc):
    s = sc([row(1), row(2)])
    assert V.no_reader(s)
    r = render(shortlist(s, [JOB1]))
    assert r.returncode != 0 and "REFUSED" in r.stderr and "never started scripts/read_next.py" in r.stderr


def test_it_is_refused_even_with_no_job_to_send(sc):
    s = sc([row(1)])
    r = render(shortlist(s, []))
    assert r.returncode != 0 and "never started scripts/read_next.py" in r.stderr


def test_final_check_calls_every_job_unread_without_the_reader(sc, tmp_path):
    s = sc([row(1)])
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    (root / "state/seen.json").write_text("[]")
    (root / "state/applications.md").write_text("")
    got = F.check(shortlist(s, [JOB1]), root=str(root))
    assert got[0][0] == "UNREAD" and "never started" in got[0][3]


def test_a_backfill_without_run_slot_is_not_refused(tmp_path):
    (tmp_path / "candidates.json").write_text(json.dumps([row(1)]))
    assert not V.no_reader(str(tmp_path))
    assert V.unread_jobs(str(tmp_path), [JOB1]) == []


def test_a_run_with_nothing_to_read_is_not_refused(sc):
    assert not V.no_reader(sc([]))


def test_the_reader_counts_as_started_when_the_time_was_already_up(sc, capsys):
    s = sc([row(1)], started_minutes_ago=81)
    assert R.main(["x", s]) == 2
    assert os.path.exists(os.path.join(s, "read_log.json")) and not V.no_reader(s)
    assert R.log(s)["printed"] == {}


def test_asking_for_the_status_does_not_count_as_a_read(sc, capsys):
    s = sc([row(1)])
    R.main(["x", s, "--status"])
    assert V.counts(s)["read_full"] == 0 and V.unread_jobs(s, [JOB1])


def test_the_reading_record_has_one_entry_per_batch(sc, capsys):
    s = sc([row(1), row(2), row(3)])
    R.main(["x", s])
    hand_in(s, [verdict("acme1-ml-engineer", fit=8), verdict("acme2-ml-engineer", fit=6)])
    rec = V.reading_record(s)
    assert len(rec) == 1
    b = rec[0]
    assert b["jobs"] == 3 and b["verdicts"] == 2
    assert b["chars"] == sum(len(row(i)["desc"]) for i in (1, 2, 3))
    assert b["printed_at"] and b["verdicts_at"] >= b["printed_at"]


def test_the_audit_names_what_is_wrong():
    ok = dict(candidates=3, read_full=3, jobs=[dict(company="A", title="T", desc="text")],
              reading=[dict(n=1, printed_at="2026-10-03T08:30:00+00:00", jobs=3, chars=13000, verdicts=3,
                            verdicts_at="2026-10-03T08:31:10+00:00")])
    rows, problems, summ = A.audit(ok)
    assert problems == [] and rows[0]["seconds"] == 70 and summ["chars"] == 13000 and summ["median_seconds"] == 70

    assert "no reading record" in A.audit(dict(candidates=200, read_full=200, jobs=[]))[1][0]
    assert A.audit(dict(candidates=0, jobs=[]))[1] == []                      # an empty noon run

    bad = dict(ok, read_full=5, reading=[dict(ok["reading"][0], verdicts=2)])
    text = " | ".join(A.audit(bad)[1])
    assert "2 of 3 jobs have a verdict" in text and "read_full says 5" in text

    # The shortlist file never keeps the job text (it is in the pack), so an empty desc there is normal.
    assert A.audit(dict(ok, jobs=[dict(company="A", title="T", desc="")]))[1] == []
