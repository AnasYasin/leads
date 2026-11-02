import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import applications  # noqa: E402

DOC = """# Applications log

| Researched | Company | Role | Location | Verdict | Docs built | Applied | Outcome |
|---|---|---|---|---|---|---|---|
| 2026-09-21 | TÜV SÜD | Data Scientist (w/m/d) | Munich | fit 7 | CV | yes 2026-09-21 | rejected |
| 2026-09-22 | Preply | AI Engineer | Berlin | fit 6 | CV, CL | no | |
| 2026-09-23 | Short Row | ML Engineer |
| not a date | Nope | X | | | | yes | |

## Older applications

Names from before the radar, one line.

DHL, Siemens Mobility,
Zalando SE
"""


def test_rows_pad_short_rows_and_skip_header(tmp_path):
    p = tmp_path / "applications.md"
    p.write_text(DOC, encoding="utf-8")
    rs = applications.rows(str(p))
    assert [r["Company"] for r in rs] == ["TÜV SÜD", "Preply", "Short Row"]
    assert rs[2]["Applied"] == "" and rs[2]["Outcome"] == ""
    assert rs[0]["Role"] == "Data Scientist (w/m/d)" and rs[0]["Researched"] == "2026-09-21"


def test_applied_is_only_the_yes_rows(tmp_path):
    p = tmp_path / "applications.md"
    p.write_text(DOC, encoding="utf-8")
    assert applications.applied(str(p)) == [("TÜV SÜD", "Data Scientist (w/m/d)")]


def test_older_names_and_missing_file(tmp_path):
    p = tmp_path / "applications.md"
    p.write_text(DOC, encoding="utf-8")
    assert applications.older_names(str(p)) == ["DHL", "Siemens Mobility", "Zalando SE"]
    assert applications.rows(str(tmp_path / "none.md")) == []
    assert applications.applied(str(tmp_path / "none.md")) == []


def test_line_is_the_inverse_of_parse():
    l = "| 2026-09-22 | Preply | AI Engineer | Berlin | fit 6 | CV, CL | no |  |"
    assert applications.line(applications.parse(l)) == l
    assert applications.parse("|---|---|") is None
