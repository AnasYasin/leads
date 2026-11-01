"""deliver.py: what goes into the shortlist issue, and when nothing does."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import deliver  # noqa: E402

MD = """# Job radar, 2026-11-01 morning, 2 new

## Band A, little or no German (2)

1. Something

---

## Run details

This part is not in the email.

## Rejected

- Analyst — E Co · fit 3 · not ML
"""


def test_the_body_stops_at_run_details_and_the_title_is_the_heading(tmp_path):
    p = tmp_path / "2026-11-01-morning.md"
    p.write_text(MD, encoding="utf-8")
    body = deliver.body_for(str(p))
    assert body.endswith("1. Something") and "Run details" not in body and "Rejected" not in body
    assert deliver.title_for(str(p), body) == "Job radar, 2026-11-01 morning, 2 new"


def test_any_heading_level_of_rejected_cuts_an_old_file(tmp_path):
    p = tmp_path / "2026-08-28-evening.md"
    p.write_text("# Job radar\n\n1. A job\n\n# Rejected\n\n- lots\n", encoding="utf-8")
    assert deliver.body_for(str(p)) == "# Job radar\n\n1. A job"


def test_a_noon_run_with_nothing_in_it_is_skipped(tmp_path, capsys):
    p = tmp_path / "2026-11-01-noon.md"
    p.write_text("# Job radar, 2026-11-01 noon, 0 new\n", encoding="utf-8")
    (tmp_path / "2026-11-01-noon.json").write_text(json.dumps(dict(slot="noon", jobs=[], also_found=[], borderline=[])))
    assert deliver.body_for(str(p)) is None
    assert deliver.main([str(p)]) == 0
    assert capsys.readouterr().out.strip() == "SKIP"
    (tmp_path / "2026-11-01-noon.json").write_text(json.dumps(dict(slot="noon", jobs=[], also_found=[dict(company="x")], borderline=[])))
    assert deliver.body_for(str(p)) is not None


def test_raw_keeps_the_whole_file_and_out_writes_the_body(tmp_path, capsys):
    p = tmp_path / "corr.md"
    p.write_text(MD, encoding="utf-8")
    out = tmp_path / "body.md"
    assert deliver.main(["--raw", str(p), "--out", str(out)]) == 0
    assert capsys.readouterr().out.strip() == "Job radar, 2026-11-01 morning, 2 new"
    assert "## Rejected" in out.read_text(encoding="utf-8")
