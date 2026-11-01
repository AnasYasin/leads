import json

import pytest

import triage as T


@pytest.fixture
def sc(tmp_path):
    rows = [dict(company="A", title="ML Engineer", prescore=5, source="ats"),
            dict(company="B", title="Growth Marketer (AI-Powered QA)", prescore=2, source="talent"),
            dict(company="C", title="Software Engineer II", prescore=1, source="linkedin"),
            dict(company="D", title="Product Specialist DACH (AI x Greentech)", prescore=1, source="arbeitnow")]
    (tmp_path / "candidates.json").write_text(json.dumps(rows))
    return tmp_path


def test_list_numbers_every_row(sc):
    out, n = T.listing(str(sc))
    lines = open(out).read().splitlines()
    assert n == 4 and lines[0].startswith("1 | 5 | A | ML Engineer")


def test_apply_removes_only_listed_rows_and_keeps_an_audit(sc):
    (sc / "title_drop.txt").write_text("2 marketing\n4: sales\n# comment\n99 out of range\n")
    n, msg = T.apply(str(sc))
    kept = json.load(open(sc / "candidates.json"))
    assert n == 2 and [r["company"] for r in kept] == ["A", "C"]
    audit = json.load(open(sc / "title_dropped.json"))
    assert [(a["row"], a["reason"]) for a in audit] == [(2, "marketing"), (4, "sales")]


def test_bare_numbers_are_accepted(sc):
    (sc / "title_drop.txt").write_text("2, 4")
    n, _ = T.apply(str(sc))
    assert n == 2


def test_refuses_to_empty_the_run(sc):
    (sc / "title_drop.txt").write_text("1 2 3 4")
    n, msg = T.apply(str(sc))
    assert n is None and msg.startswith("refused")
    assert len(json.load(open(sc / "candidates.json"))) == 4
    n, _ = T.apply(str(sc), force=True)
    assert n == 4


def test_missing_drop_file_changes_nothing(sc):
    n, msg = T.apply(str(sc))
    assert n is None and msg.startswith("no title_drop")
