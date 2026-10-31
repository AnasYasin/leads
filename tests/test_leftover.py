import json

import pytest

import leftover as L


def row(co, ti, **kw):
    return dict(id=("%s-%s" % (co, ti)).lower().replace(" ", "-"), company=co, title=ti,
                url="https://%s/%s" % (co.lower(), ti.lower().replace(" ", "-")), source="ATS/x", desc="PyTorch", **kw)


@pytest.fixture
def repo(tmp_path):
    root, sc = tmp_path / "repo", tmp_path / "sc"
    root.mkdir(exist_ok=True)
    sc.mkdir()
    (root / "state/seen.json").write_text("[]")
    (root / "state/applications.md").write_text("")
    return root, sc


def run(sc, cands, slot="morning", date="2026-09-30"):
    (sc / "candidates.json").write_text(json.dumps(cands))
    (sc / "run_slot.json").write_text(json.dumps({"date": date, "slot": slot}))


def names(root):
    return [e["company"] for e in L.load(str(root))]


A, B, C, D = row("Alpha", "ML Engineer"), row("Beta", "CV Engineer"), row("Gamma", "LLM Engineer"), row("Delta", "Data Scientist")
M = "2026-09-30 morning"


def test_morning_saves_what_it_did_not_read(repo):
    root, sc = repo
    run(sc, [A, B, C])
    sl = dict(date="2026-09-30", slot="morning", jobs=[dict(company="Alpha", title="ML Engineer")],
              rejected=[dict(company="Beta", title="CV Engineer", reason="fit 4")])
    msg = L.after_render(str(sc), sl, str(root))
    pool = L.load(str(root))
    assert [e["company"] for e in pool] == ["Gamma"]
    assert pool[0]["first"] == M and pool[0]["last"] == "2026-09-30"
    assert msg.endswith("state/backlog_done.json +2")


def test_evening_refreshes_removes_read_and_adds(repo):
    root, sc = repo
    L.save([dict(C, first=M, last="2026-09-30"), dict(D, first=M, last="2026-09-30")], str(root))
    run(sc, [C, B], slot="evening")                     # C still unread, B new and unread, D read
    sl = dict(date="2026-09-30", slot="evening", rejected=[dict(company="Delta", title="Data Scientist")])
    msg = L.after_render(str(sc), sl, str(root))
    pool = {e["company"]: e for e in L.load(str(root))}
    assert set(pool) == {"Gamma", "Beta"}
    assert pool["Gamma"]["first"] == M                    # first kept on refresh
    assert pool["Beta"]["first"] == "2026-09-30 evening"
    assert "1 added, 1 refreshed, 1 read (this or an earlier run) and removed" in msg


def test_a_job_the_noon_run_rejected_never_comes_back_in_the_evening(repo):
    root, sc = repo
    L.save([dict(C, first=M, last="2026-09-30")], str(root))
    L.load_for_noon(str(sc), str(root))
    (sc / "run_slot.json").write_text(json.dumps({"date": "2026-09-30", "slot": "noon"}))
    L.after_render(str(sc), dict(date="2026-09-30", slot="noon", rejected=[dict(company="Gamma", title="LLM Engineer")]), str(root))
    assert names(root) == []
    sc2 = sc.parent / "sc2"
    sc2.mkdir()
    run(sc2, [C, D], slot="evening")                   # the evening collects Gamma again and does not read it
    L.after_render(str(sc2), dict(date="2026-09-30", slot="evening"), str(root))
    assert names(root) == ["Delta"]


def test_the_same_job_from_two_sources_is_one_row(repo):
    root, sc = repo
    L.save([dict(A, first=M, last="2026-09-30")], str(root))
    other = dict(A, id="alpha-ml-engineer-berlin", source="talent.com", url="https://talent/alpha")
    run(sc, [other], slot="evening")
    L.after_render(str(sc), dict(date="2026-09-30", slot="evening"), str(root))
    pool = L.load(str(root))
    assert len(pool) == 1 and pool[0]["id"] == A["id"] and pool[0]["first"] == M


def test_done_signatures_are_unique(repo):
    root, sc = repo
    run(sc, [])
    sl = dict(date="2026-09-30", slot="morning", rejected=[dict(company="Beta", title="CV Engineer")])
    L.after_render(str(sc), sl, str(root))
    run(sc, [], slot="evening")
    L.after_render(str(sc), dict(sl, slot="evening"), str(root))
    assert [d["company"] for d in L.load_done(str(root))] == ["Beta"]


def test_rows_not_seen_unread_for_two_days_are_pruned(repo):
    root, sc = repo
    L.save([dict(C, first="2026-09-27 evening", last="2026-09-27"), dict(D, first="2026-09-28 morning", last="2026-09-28")], str(root))
    run(sc, [])
    L.after_render(str(sc), dict(date="2026-09-30", slot="morning"), str(root))
    assert names(root) == ["Delta"]


def test_noon_loads_the_list_minus_sent_since_and_applied(repo):
    root, sc = repo
    L.save([dict(A, first=M, last="2026-09-30"), dict(B, first=M, last="2026-09-30"),
            dict(C, first=M, last="2026-09-30"), dict(D, first=M, last="2026-09-30")], str(root))
    (root / "state/seen.json").write_text(json.dumps([
        dict(company="Alpha", title="ML Engineer", url=A["url"], sent="2026-09-30", slot="evening"),     # after: drop
        dict(company="Delta", title="Data Scientist", url=D["url"], sent="2026-08-06")]))                # before: a second opening, keep
    (root / "state/applications.md").write_text("| 2026-09-30 | Beta | CV Engineer | Berlin | apply | CV | yes 2026-09-30 | |\n")
    n, sent, applied = L.load_for_noon(str(sc), str(root))
    cands = json.load(open(sc / "candidates.json"))
    assert (n, sent, applied) == (2, 1, 1) and sorted(c["company"] for c in cands) == ["Delta", "Gamma"]
    assert "first" not in cands[0] and "prescore" in cands[0]


def test_noon_removes_what_it_processed_and_keeps_the_rest(repo):
    root, sc = repo
    L.save([dict(A, first=M, last="2026-09-30"), dict(B, first=M, last="2026-09-30"),
            dict(C, first=M, last="2026-09-30"), dict(D, first=M, last="2026-09-30")], str(root))
    (root / "state/seen.json").write_text(json.dumps([dict(company="Delta", title="Data Scientist", url=D["url"], sent="2026-09-30", slot="noon")]))
    L.load_for_noon(str(sc), str(root))                # Delta dropped as sent since
    (sc / "run_slot.json").write_text(json.dumps({"date": "2026-09-30", "slot": "noon"}))
    sl = dict(date="2026-09-30", slot="noon", jobs=[dict(company="Alpha", title="ML Engineer")],
              rejected=[dict(company="Beta", title="CV Engineer")])
    msg = L.after_render(str(sc), sl, str(root))
    assert names(root) == ["Gamma"]                    # not reached, stays
    assert msg == "state/leftover.json: noon processed 3, 1 still unread, 1 in the list; state/backlog_done.json +2"


def test_noon_keeps_rows_added_after_it_loaded(repo):
    root, sc = repo
    L.save([dict(A, first=M, last="2026-09-30")], str(root))
    L.load_for_noon(str(sc), str(root))
    L.save(L.load(str(root)) + [dict(B, first=M, last="2026-09-30")], str(root))
    (sc / "run_slot.json").write_text(json.dumps({"date": "2026-09-30", "slot": "noon"}))
    L.after_render(str(sc), dict(date="2026-09-30", slot="noon", jobs=[dict(company="Alpha", title="ML Engineer")]), str(root))
    assert names(root) == ["Beta"]


def test_a_render_outside_a_run_leaves_everything_alone(repo):
    root, sc = repo
    L.save([dict(C, first=M, last="2026-09-30")], str(root))
    (sc / "candidates.json").write_text(json.dumps([A]))
    assert L.after_render(str(sc), dict(date="2026-09-30", slot="backfill", rejected=[dict(company="Gamma", title="LLM Engineer")]), str(root)) is None
    assert names(root) == ["Gamma"] and L.load_done(str(root)) == []


def test_a_second_opening_stays_a_second_opening_at_noon(repo):
    """Preply, 29 Sep: the filter let 'AI Learning' through beside the sent 'AI Marketplace'.
    At noon there is no collected pool, so the sent job's live link has to come with the row."""
    import final_check
    root, sc = repo
    old = "https://jobs.ashbyhq.com/preply/old"
    (root / "state/seen.json").write_text(json.dumps([dict(company="Preply", title="Senior Applied AI Scientist (AI Marketplace)",
                                                     url=old, sent="2026-08-03")]))
    new = dict(row("Preply", "Senior Applied AI Scientist (AI Learning)"), url="https://jobs.ashbyhq.com/preply/new",
               similar_to_sent="Preply | Senior Applied AI Scientist (AI Marketplace) (sent 2026-08-03)")
    (sc / "ats.json").write_text(json.dumps([dict(url=old), dict(url=new["url"])]))
    run(sc, [new], slot="evening")
    L.after_render(str(sc), dict(date="2026-09-30", slot="evening"), str(root))
    noon = sc.parent / "noon"
    noon.mkdir()
    n, sent, _ = L.load_for_noon(str(noon), str(root))
    assert (n, sent) == (1, 0)
    (noon / "shortlist.json").write_text(json.dumps(dict(date="2026-10-01", slot="noon", jobs=[
        dict(company="Preply", title="Senior Applied AI Scientist (AI Learning)", apply_url=new["url"])])))
    assert final_check.check(str(noon / "shortlist.json"), root=str(root))[0][0] == "SECOND OPENING"
