import json

import final_check as F


def test_repeat_second_opening_applied_and_ok(tmp_path):
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    (root / "state/seen.json").write_text(json.dumps([
        dict(id="p", company="Preply", title="Senior Applied AI Scientist (AI Marketplace)", url="https://jobs.ashbyhq.com/preply/old", sent="2026-08-03"),
        dict(id="a", company="ARRK Engineering GmbH", title="Machine Learning Engineer Automatisiertes Fahren (m/w/d)",
             location="München", url="https://arrk/1", sent="2026-09-06"),
        dict(id="t", company="Today Co", title="ML Engineer", url="https://today/1", sent="2026-09-29")]))
    (root / "state/applications.md").write_text("| 2026-09-02 | NiCE | Senior AI Software Engineer, req 11563 | Berlin | apply | CV | yes 2026-09-03 | |\n")
    sc = tmp_path / "sc"
    sc.mkdir()
    (sc / "ats.json").write_text(json.dumps([dict(url="https://jobs.ashbyhq.com/preply/old"), dict(url="https://jobs.ashbyhq.com/preply/new")]))
    (sc / "shortlist.json").write_text(json.dumps(dict(date="2026-09-29", jobs=[
        dict(company="Preply", title="Senior Applied AI Scientist (AI Learning)", apply_url="https://jobs.ashbyhq.com/preply/new"),
        dict(company="Mitsui Chemicals Group", title="Machine Learning Engineer Automatisiertes Fahren (m/w/d)",
             location="Munich", apply_url="https://li/9", desc="GESELLSCHAFT ARRK Engineering GmbH. Wir suchen."),
        dict(company="NiCE", title="Senior AI Software Engineer", apply_url="https://nice/1"),
        dict(company="Today Co", title="ML Engineer", apply_url="https://today/1"),   # its own first render
        dict(company="Brand New", title="Computer Vision Engineer", apply_url="https://new/1")])))
    got = {(r[1], r[0]) for r in F.check(str(sc / "shortlist.json"), root=str(root))}
    assert ("Preply", "SECOND OPENING") in got
    assert ("Mitsui Chemicals Group", "REPEAT") in got
    assert ("NiCE", "APPLIED") in got
    assert ("Today Co", "OK") in got and ("Brand New", "OK") in got


def test_same_day_send_by_another_run_is_a_repeat(tmp_path):
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    (root / "state/seen.json").write_text(json.dumps([
        dict(id="m", company="Morning Co", title="ML Engineer", url="https://m/1", sent="2026-09-30", slot="morning"),
        dict(id="n", company="Noon Co", title="CV Engineer", url="https://n/1", sent="2026-09-30", slot="noon")]))
    sc = tmp_path / "sc"
    sc.mkdir()
    (sc / "shortlist.json").write_text(json.dumps(dict(date="2026-09-30", slot="noon", jobs=[
        dict(company="Morning Co", title="ML Engineer", apply_url="https://m/1"),
        dict(company="Noon Co", title="CV Engineer", apply_url="https://n/1")])))   # its own first render
    got = {(r[1], r[0]) for r in F.check(str(sc / "shortlist.json"), root=str(root))}
    assert ("Morning Co", "REPEAT") in got and ("Noon Co", "OK") in got
