
import pytest

import rejected as R


@pytest.mark.parametrize("reason", [
    "Drop band: 'Sehr gute Deutschkenntnisse (C1)'.",
    "Language drop: 'Speaks excellent German and English.'",
    "Disqualified on German: 'Fluent German and English communication skills'.",
    "'NATO-aligned nationality or close ally citizenship is required' - automatic disqualifier.",
    "German in the drop band: 'Fließend in Deutsch und Englisch'",
    "Fluent German.",
])
def test_hard_kills(reason):
    assert R.hard(reason)


@pytest.mark.parametrize("reason", [
    "B2 German would have been acceptable, but the stack is Java.",
    "German a plus reads fine, but the prior rejection settles it.",
    "Kubernetes is required and he has Ray on GKE.",
    "Location. LinkedIn geo-tags it Germany but the body is Hove, UK.",
    "Staff title - automatic out on the seniority rule. German is only a plus.",
    "", None,
])
def test_not_hard(reason):
    assert not R.hard(reason)


def test_merge_keeps_only_hard_and_skips_bad_rows():
    rows = []
    added = R.merge(rows, [
        dict(company="A GmbH", title="AI Engineer", fit=7, reason="Drop band: 'sehr gute Deutschkenntnisse'"),
        dict(company="B", title="ML Engineer", fit=5, reason="No deep learning in the role."),
        dict(company="C", title="ML Engineer", fit=7, reason="ALREADY SENT 2026-09-20 at fit 7."),
        dict(company=None, title=None, fit=None, reason=None),
        dict(company="", title="x", reason="Drop band"),
    ], "2026-09-28")
    assert added == 1
    assert [r["company"] for r in rows] == ["A GmbH"]
    assert rows[0]["first"] == rows[0]["last"] == "2026-09-28"


def test_merge_same_job_again_moves_last_date():
    rows = []
    kill = dict(company="A GmbH", title="AI Engineer (m/w/d)", fit=7, reason="Drop band: C1 Deutsch erforderlich")
    R.merge(rows, [kill], "2026-09-20")
    assert R.merge(rows, [dict(kill, title="AI Engineer (w/m/d)")], "2026-09-28") == 0
    assert len(rows) == 1 and rows[0]["first"] == "2026-09-20" and rows[0]["last"] == "2026-09-28"


def test_merge_prunes_old_entries():
    rows = [dict(id="x", company="Old", title="ML Engineer", last="2026-07-01", first="2026-07-01")]
    R.merge(rows, [], "2026-09-28")
    assert rows == []


def test_active_window_boundary():
    rows = [dict(company="A", title="t", last="2026-09-14"), dict(company="B", title="t", last="2026-09-13")]
    act = R.active(rows, "2026-09-28")
    assert [r["company"] for r in act] == ["A"]


def test_split_skips_matching_candidate_only():
    rows = [dict(company="EXXETA", title="(Senior) Data Scientist - Physical AI & Computer Vision (all genders)",
                 last="2026-09-28", reason="Drop band")]
    kept, skipped = R.split([
        dict(company="EXXETA", title="(Senior) Data Scientist - Physical AI & Computer Vision (all genders)"),
        dict(company="Brandnew Robotics", title="Machine Learning Engineer"),
        dict(company=None, title=None),
    ], rows, "2026-09-29")
    assert [j["company"] for j, _ in skipped] == ["EXXETA"]
    assert len(kept) == 2


def test_split_with_empty_memory_keeps_all():
    kept, skipped = R.split([dict(company="A", title="B")], [], "2026-09-29")
    assert len(kept) == 1 and skipped == []


def test_parse_md(tmp_path):
    p = tmp_path / "2026-09-28-evening.md"
    p.write_text("# x\n\n## Rejected\n\n"
                 "- AI Engineer (m/w/d) — RENK GmbH · fit 8 · Language drop: 'sehr gute Deutschkenntnisse'\n"
                 "- ML Engineer — Somefirm · fit ? · unreadable\n"
                 "not a line\n", encoding="utf-8")
    rows = R.parse_md(str(p))
    assert rows[0]["company"] == "RENK GmbH" and rows[0]["fit"] == 8
    assert rows[1]["fit"] is None


def test_parse_md_without_section(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("# nothing rejected\n", encoding="utf-8")
    assert R.parse_md(str(p)) == []


@pytest.mark.parametrize("reason", [
    "No security clearance required, but fit is low.",
    "Fluent German not required; the stack is wrong.",
    "EU citizenship not needed, but 8+ years asked.",
])
def test_negated_requirements_are_not_hard(reason):
    assert not R.hard(reason)


def test_german_or_english_is_not_a_kill():
    assert not R.hard("Koara: 'Sehr gute Deutsch- oder Englischkenntnisse' - fit too low")
