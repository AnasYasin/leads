import datetime
import json

import pytest

import prune_packs as P

D0 = datetime.date(2026, 10, 20)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "jobs").mkdir()
    packs = [
        dict(id="old-gone", company="Gone GmbH", title="ML Engineer", sent="2026-09-01", apply_url="https://x/gone", location="Berlin"),
        dict(id="old-live", company="Live GmbH", title="CV Engineer", sent="2026-09-01", apply_url="https://x/live", location="Berlin"),
        dict(id="old-mixed", company="Mixed GmbH", title="AI Engineer", sent="2026-09-01", apply_url="https://x/gone2",
             fallback_url="https://x/unsure", location="Berlin"),
        dict(id="old-repost", company="Repost AG", title="AI Experte (m/w/d)", sent="2026-09-01", apply_url="https://x/gone3", location="Bonn"),
        dict(id="old-applied", company="Applied GmbH", title="Data Scientist", sent="2026-09-01", apply_url="https://x/gone4", location="Berlin"),
        dict(id="young-gone", company="Young GmbH", title="ML Engineer", sent="2026-10-19", apply_url="https://x/gone5", location="Berlin"),
        dict(id="no-links", company="Nolinks GmbH", title="ML Engineer", sent="2026-09-01", location="Berlin"),
    ]
    for p in packs:
        p["pack"] = "jobs/%s.md" % p["id"]
        (tmp_path / p["pack"]).write_text("---\nid: %s\n---\n" % p["id"])
    (tmp_path / "jobs" / "index.json").write_text(json.dumps(packs))
    (tmp_path / "state/applications.md").write_text(
        "| Researched | Company | Role | Location | Verdict | Docs built | Applied | Outcome |\n|---|---|---|---|---|---|---|---|\n"
        "| 2026-09-02 | Applied GmbH | Data Scientist | Berlin | apply | CV | yes 2026-09-03 | |\n")
    sc = tmp_path / "sc"
    sc.mkdir()
    (sc / "ba.json").write_text(json.dumps([dict(company="Repost AG", title="AI Experte (m/w/d)", location="Bonn", url="https://ba/new")]))
    return tmp_path, sc


def fake_check(u):
    if "gone" in u:
        return ("GONE", "HTTP 404")
    if "unsure" in u:
        return ("UNSURE", "HTTP 403")
    return ("LIVE", "HTTP 200")


def go(repo, day, dry=False, check=fake_check, sc=None):
    root, scratch = repo
    return P.run(str(sc or scratch), root=str(root), today=day, dry=dry, check=check, apps=str(root / "state/applications.md"))


def exists(repo, pid):
    return (repo[0] / "jobs" / (pid + ".md")).exists()


def test_first_strike_never_deletes(repo):
    counts, kept, deleted = go(repo, D0)
    assert deleted == [] and counts["first_strike"] == 1
    assert exists(repo, "old-gone")


def test_second_strike_two_days_later_deletes_only_the_gone_one(repo):
    go(repo, D0)
    counts, kept, deleted = go(repo, D0 + datetime.timedelta(days=2))
    assert [d["pack"] for d in deleted] == ["jobs/old-gone.md"]
    assert not exists(repo, "old-gone")
    for pid in ("old-live", "old-mixed", "old-repost", "old-applied", "young-gone", "no-links"):
        assert exists(repo, pid), pid
    log = json.load(open(repo[0] / "state/prune.json"))["log"]
    assert log[-1]["company"] == "Gone GmbH" and log[-1]["first_gone"] == D0.isoformat()


def test_a_check_within_two_days_is_skipped(repo):
    go(repo, D0)
    for d in (0, 1):
        counts, _, deleted = go(repo, D0 + datetime.timedelta(days=d))
        assert counts == {"skipped": D0.isoformat()} and deleted == [] and exists(repo, "old-gone")
    assert len(go(repo, D0 + datetime.timedelta(days=1), dry=True)[2]) == 1   # a dry run is never skipped


def test_repost_in_pool_is_kept(repo):
    go(repo, D0)
    go(repo, D0 + datetime.timedelta(days=2))
    assert exists(repo, "old-repost")


def test_live_again_resets_the_strike(repo):
    go(repo, D0)
    go(repo, D0 + datetime.timedelta(days=2), check=lambda u: ("LIVE", "back"))
    assert "old-gone" not in json.load(open(repo[0] / "state/prune.json"))["pending"]
    _, _, deleted = go(repo, D0 + datetime.timedelta(days=4))
    assert deleted == []                      # needs a fresh first strike again


def test_no_pool_never_deletes(repo, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    go(repo, D0, sc=empty)
    counts, _, deleted = go(repo, D0 + datetime.timedelta(days=3), sc=empty)
    assert deleted == [] and counts["no_pool"] >= 1 and exists(repo, "old-gone")


def test_dry_run_changes_nothing(repo):
    go(repo, D0)
    before = (repo[0] / "state/prune.json").read_text()
    counts, _, deleted = go(repo, D0 + datetime.timedelta(days=2), dry=True)
    assert len(deleted) == 1 and exists(repo, "old-gone")
    assert (repo[0] / "state/prune.json").read_text() == before


def test_kept_counts(repo):
    _, kept, _ = go(repo, D0)
    assert kept == {"young": 1, "applied": 1}


def test_verdict():
    assert P.verdict([]) == "UNSURE"
    assert P.verdict([("GONE", ""), ("GONE", "")]) == "GONE"
    assert P.verdict([("GONE", ""), ("UNSURE", "")]) == "UNSURE"
    assert P.verdict([("GONE", ""), ("LIVE", "")]) == "LIVE"


def test_applied_under_an_edited_title_is_kept(tmp_path):
    # review, 29 Sep 2026: these four real applied packs failed the strict guard and were deleted
    (tmp_path / "jobs").mkdir()
    pairs = [("Delivery Hero", "Senior Machine Learning Engineer - (Logistics, Optimization)", "Senior Machine Learning Engineer, Logistics Optimization"),
             ("NiCE", "Senior AI Software Engineer", "Senior AI Software Engineer, req 11563"),
             ("Libra Technology GmbH", "Senior AI Evals Engineer", "Senior AI Evals Engineer - Libra Legal AI Assistant"),
             ("TÜV SÜD", "Data Scientist (w/m/d)", "Data Scientist (w/m/d) - 7641")]
    packs, rows = [], []
    for i, (co, pack_title, logged) in enumerate(pairs):
        p = dict(id="p%d" % i, company=co, title=pack_title, sent="2026-09-01", apply_url="https://x/gone%d" % i,
                 location="Berlin", pack="jobs/p%d.md" % i)
        (tmp_path / p["pack"]).write_text("---\n")
        packs.append(p)
        rows.append("| 2026-09-02 | %s | %s | Berlin | apply | CV | yes 2026-09-03 | |" % (co, logged))
    packs.append(dict(id="stamped", company="Other GmbH", title="ML Engineer", sent="2026-09-01", apply_url="https://x/gone9",
                      location="Berlin", pack="jobs/stamped.md", applied="2026-09-05 10:00"))
    (tmp_path / "jobs" / "stamped.md").write_text("---\n")
    (tmp_path / "jobs" / "index.json").write_text(json.dumps(packs))
    (tmp_path / "state/applications.md").write_text("\n".join(rows) + "\n")
    sc = tmp_path / "sc"
    sc.mkdir()
    (sc / "ba.json").write_text(json.dumps([dict(company="Unrelated", title="Cook", url="https://ba/1")]))
    for day in (D0, D0 + datetime.timedelta(days=2)):
        counts, kept, deleted = P.run(str(sc), root=str(tmp_path), today=day, check=fake_check,
                                      apps=str(tmp_path / "state/applications.md"))
    assert deleted == [] and kept["applied"] == 5


def test_board_failed_this_run_is_skipped(repo):
    root, sc = repo
    (sc / "ats.json.report").write_text(json.dumps([dict(company="Gone GmbH", slug="gonegmbh", kind="greenhouse", n=0, err="DNS")]))
    go(repo, D0)
    counts, _, deleted = go(repo, D0 + datetime.timedelta(days=2))
    assert deleted == [] and counts["board_failed"] == 1 and exists(repo, "old-gone")


def test_index_is_rebuilt_after_a_deletion(repo):
    root, _ = repo
    (root / "scripts").mkdir(exist_ok=True)
    go(repo, D0)
    go(repo, D0 + datetime.timedelta(days=2))
    idx = json.load(open(root / "jobs" / "index.json"))
    assert all(p["pack"] != "jobs/old-gone.md" for p in idx)
