"""retext.py: text for a textless row from a link found by hand, and the no_text gate that retires
the rest. Added 29 Oct 2026."""
import json
import os

import decisions as D
import read_next as R
import retext as T
import verdict as V

TEXT = "We build detection models for retail shelves and deploy them on edge devices in stores. " * 6


def sc(tmp_path):
    rows = [dict(id="acme-ml-engineer", company="Acme", title="ML Engineer", source="getro:X", url="https://acme.example/jobs", desc=""),
            dict(id="beta-ml-engineer", company="Beta", title="ML Engineer", source="getro:X", url="https://beta.example/jobs", desc="")]
    (tmp_path / "candidates.json").write_text(json.dumps(rows))
    (tmp_path / "no_text.json").write_text(json.dumps([dict(job="Acme | ML Engineer", url="https://acme.example/jobs", why="0 characters")]))
    (tmp_path / "run_slot.json").write_text(json.dumps({"date": "2026-10-29", "slot": "noon", "started": "2026-10-29T11:00:00+00:00"}))
    return str(tmp_path)


def test_a_found_link_puts_the_text_on_the_row(tmp_path):
    s = sc(tmp_path)
    ok, msg = T.apply(s, "acme-ml-engineer", "https://acme.example/careers/ml", fetch=lambda row, url: dict(row, desc=TEXT, desc_src="json-ld"))
    assert ok and "characters" in msg
    row = next(j for j in R.candidates(s) if j["id"] == "acme-ml-engineer")
    assert row["desc"] == TEXT and row["url"] == "https://acme.example/careers/ml" and row["url_card"] == "https://acme.example/jobs"
    assert json.load(open(os.path.join(s, "no_text.json"))) == []
    assert [j for j, _ in T.textless(s)][0]["id"] == "beta-ml-engineer"


def test_a_failed_fetch_changes_nothing(tmp_path):
    s = sc(tmp_path)
    ok, msg = T.apply(s, "acme-ml-engineer", "https://acme.example/x", fetch=lambda row, url: dict(row, error="HTTP 403"))
    assert not ok and "HTTP 403" in msg and R.candidates(s)[0]["desc"] == ""
    assert not T.apply(s, "nobody", "https://x")[0]


def test_no_text_retires_an_unprinted_row_and_is_remembered(tmp_path):
    s = sc(tmp_path)
    rows = {R.cid(j): j for j in R.candidates(s)}
    clean, why = V.check(dict(id="beta-ml-engineer", gate="no_text", reason="Searched the web, Beta lists no such job; Getro card only."), rows, printed={})
    assert why is None and clean["gate"] == "no_text" and clean["verdict"] == "reject"
    # the draft lists read `verdict` straight off the stored dict; 30 Oct 2026 the key was missing and --draft crashed
    json.dump({"beta-ml-engineer": clean}, open(os.path.join(s, "verdicts.json"), "w"))
    assert [(r["company"], r["gate"]) for r in V.lists(s)["rejected"]] == [("Beta", "no_text")]
    # a row with text cannot take the gate, and a bare reason is refused
    rows["beta-ml-engineer"]["desc"] = TEXT
    assert "has text" in V.check(dict(id="beta-ml-engineer", gate="no_text", reason="Searched the web for it and found nothing."), rows, {})[1]
    rows["beta-ml-engineer"]["desc"] = ""
    assert "reason" in V.check(dict(id="beta-ml-engineer", gate="no_text", reason="none"), rows, {})[1]
    # the verdict is remembered, so the next run's filter skips the same textless row
    cands = R.candidates(s)
    D.record({"beta-ml-engineer": clean}, cands, "2026-10-29", "noon", str(tmp_path))
    kept, remembered = D.split([dict(cands[1])], D.load(str(tmp_path)), "2026-10-30", set())
    assert kept == [] and remembered[0][1]["gate"] == "no_text"
