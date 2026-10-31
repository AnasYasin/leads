"""Reproductions of the 29 Sep 2026 review findings. Each test was written to fail on the code
before its fix, to prove the finding real, and passes after it."""
import json

import pytest
import yaml

import cfg
import leftover as L
from conftest import ROOT


def row(co, ti, url, **kw):
    return dict(id=("%s-%s" % (co, ti)).lower().replace(" ", "-"), company=co, title=ti, url=url,
                source="ATS/x", desc="PyTorch", **kw)


@pytest.fixture
def repo(tmp_path):
    root, sc = tmp_path / "repo", tmp_path / "sc"
    root.mkdir(exist_ok=True)
    sc.mkdir()
    (root / "state/seen.json").write_text("[]")
    (root / "state/applications.md").write_text("")
    return root, sc


def run(sc, cands, slot, date="2026-09-30", pool=None):
    (sc / "candidates.json").write_text(json.dumps(cands))
    (sc / "run_slot.json").write_text(json.dumps({"date": date, "slot": slot}))
    (sc / "ats.json").write_text(json.dumps([dict(url=u) for u in (pool or [c["url"] for c in cands])]))


LEARN = row("Preply", "Senior Applied AI Scientist (AI Learning)", "https://jobs.ashbyhq.com/preply/learn")
MARKET = row("Preply", "Senior Applied AI Scientist (AI Marketplace)", "https://jobs.ashbyhq.com/preply/market")


# 1. Two openings at one employer must stay two backlog rows.
def test_two_openings_at_one_employer_stay_two_backlog_rows(repo):
    root, sc = repo
    run(sc, [LEARN], "morning", pool=[LEARN["url"], MARKET["url"]])
    L.after_render(str(sc), dict(date="2026-09-30", slot="morning"), str(root))
    run(sc, [MARKET], "evening", pool=[LEARN["url"], MARKET["url"]])
    L.after_render(str(sc), dict(date="2026-09-30", slot="evening"), str(root))
    assert sorted(e["title"] for e in L.load(str(root))) == sorted([LEARN["title"], MARKET["title"]])


def test_the_same_job_from_two_sources_is_still_one_row(repo):
    root, sc = repo
    run(sc, [LEARN], "morning")
    L.after_render(str(sc), dict(date="2026-09-30", slot="morning"), str(root))
    copy = dict(LEARN, id="other-id", source="linkedin", url="https://www.linkedin.com/jobs/view/123")
    run(sc, [copy], "evening", pool=[copy["url"], LEARN["url"]])
    L.after_render(str(sc), dict(date="2026-09-30", slot="evening"), str(root))
    assert len(L.load(str(root))) == 1


# 2. A second opening whose twin was sent after it entered the backlog is still read at noon.
def test_a_second_opening_survives_a_later_send_of_its_twin(repo):
    root, sc = repo
    both = [LEARN["url"], MARKET["url"]]
    run(sc, [LEARN], "morning", pool=both)
    L.after_render(str(sc), dict(date="2026-09-30", slot="morning"), str(root))
    # The evening collects both, sends Marketplace and leaves Learning unread.
    run(sc, [LEARN], "evening", pool=both)
    sl = dict(date="2026-09-30", slot="evening", jobs=[dict(company="Preply", title=MARKET["title"], apply_url=MARKET["url"])])
    L.after_render(str(sc), sl, str(root))
    (root / "state/seen.json").write_text(json.dumps([dict(company="Preply", title=MARKET["title"], url=MARKET["url"],
                                                     urls=[MARKET["url"]], sent="2026-09-30", slot="evening")]))
    noon = sc.parent / "noon"
    noon.mkdir()
    n, sent, _ = L.load_for_noon(str(noon), str(root))
    assert (n, sent) == (1, 0)


def test_a_real_repeat_sent_later_is_still_dropped_at_noon(repo):
    root, sc = repo
    run(sc, [LEARN], "morning")
    L.after_render(str(sc), dict(date="2026-09-30", slot="morning"), str(root))
    (root / "state/seen.json").write_text(json.dumps([dict(company="Preply", title=LEARN["title"], url=LEARN["url"],
                                                     sent="2026-09-30", slot="evening")]))
    noon = sc.parent / "noon"
    noon.mkdir()
    assert L.load_for_noon(str(noon), str(root))[:2] == (0, 1)


# 4. A blank or empty entry in a description list must not crash or match everything.
@pytest.mark.parametrize("bad", [None, ""])
def test_a_blank_description_term_is_ignored(tmp_path, monkeypatch, bad):
    import importlib
    import prescore
    data = yaml.safe_load(open(ROOT + "/config/radar.yaml", encoding="utf-8"))
    data["prescore"]["desc_plus"].append(bad)
    data["prescore"]["infra"].append(bad)
    p = tmp_path / "radar.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True))
    monkeypatch.setenv("RADAR_CONFIG", str(p))
    cfg._cache.clear()
    try:
        prescore = importlib.reload(prescore)
        assert prescore.desc_points("nothing relevant here") == 0
    finally:
        monkeypatch.delenv("RADAR_CONFIG")
        cfg._cache.clear()
        importlib.reload(prescore)


# 5. A noon run forced to collect (--collect) saves its unread rows like any other collecting run.
def test_a_forced_collection_at_noon_saves_its_unread_rows(repo):
    root, sc = repo
    run(sc, [LEARN, MARKET], "noon")                   # no leftover_loaded.json: it collected
    L.after_render(str(sc), dict(date="2026-09-30", slot="noon", jobs=[dict(company="Preply", title=LEARN["title"])]), str(root))
    assert [e["title"] for e in L.load(str(root))] == [MARKET["title"]]


# 6. One malformed row must not stop the fetch for every other row.
def test_one_bad_row_does_not_stop_the_fetch(tmp_path):
    import fetch_desc as F
    rows = [dict(company="A", title="ML Engineer", source="linkedin"),              # no li_id
            dict(company="B", title="CV Engineer", source="linkedin", li_id="1")]
    (tmp_path / "candidates.json").write_text(json.dumps(rows))

    def fn(j):
        return dict(j, desc="PyTorch " * 60 + j["li_id"])      # KeyError on the first row, as read_linkedin does
    s = F.run(str(tmp_path), {"linkedin": fn})
    out = {r["company"]: r for r in json.load(open(tmp_path / "candidates.json"))}
    assert out["B"]["desc"].startswith("PyTorch") and not out["A"].get("desc") and s["failed"] == 1


# 10. A capitalised city in location_bonus still matches.
def test_location_bonus_ignores_case(tmp_path, monkeypatch):
    import importlib
    import prescore
    data = yaml.safe_load(open(ROOT + "/config/radar.yaml", encoding="utf-8"))
    data["prescore"]["location_bonus"] = {"Berlin": 1}
    p = tmp_path / "radar.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True))
    monkeypatch.setenv("RADAR_CONFIG", str(p))
    cfg._cache.clear()
    try:
        prescore = importlib.reload(prescore)
        assert "+1 berlin" in prescore.score(dict(title="X", company="Y", location="Berlin, Germany"), no_desc=0)[1]
    finally:
        monkeypatch.delenv("RADAR_CONFIG")
        cfg._cache.clear()
        importlib.reload(prescore)
