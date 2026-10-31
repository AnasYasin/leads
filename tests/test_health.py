import json

import pytest

import health as H


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "PATH", str(tmp_path / "state/health.json"))
    monkeypatch.setattr(H, "CANDS", str(tmp_path / "state/health_candidates.json"))
    (tmp_path / "shortlists").mkdir()
    return tmp_path


def run(tmp_path, sources, boards, cands=()):
    sc = tmp_path / "sc"
    sc.mkdir(exist_ok=True)
    for f in sc.iterdir():
        f.unlink()
    for s, n in sources.items():
        (sc / (s + ".json")).write_text(json.dumps([{}] * n))
    (sc / "ats.json.report").write_text(json.dumps(
        [dict(kind=k.split("|")[0], slug=k.split("|")[1], n=n, err=e) for k, (n, e) in boards.items()]))
    (sc / "candidates.json").write_text(json.dumps(list(cands)))
    H.main([str(sc), "--skipped", ",".join(s for s in H.SOURCES if s not in sources)])
    return json.load(open(H.PATH))["runs"][-1]["flags"]


BASE = {"ba": 700, "ats": 5000, "xing": 300, "linkedin": 90, "talent": 300, "arbeitnow": 1400, "stepstone": 200}
BOARDS = {"ashby|good": (10, ""), "greenhouse|dns": (0, "dns fail"), "personio|empty": (0, "")}


def test_first_run_lists_only_failing_boards(env):
    f = run(env, BASE, BOARDS)
    assert len(f) == 1 and f[0].startswith("FIRST RUN 3 boards polled, 2 answered, 1 failed")
    assert "greenhouse|dns" in f[0]


def test_dead_empty_new_low_zero(env):
    for _ in range(3):
        f = run(env, BASE, BOARDS)
    assert any(x.startswith("BOARD DEAD greenhouse|dns") for x in f)
    assert any(x.startswith("BOARD EMPTY personio|empty") for x in f)
    f = run(env, dict(BASE, xing=100, linkedin=0), dict(BOARDS, **{"join|new": (3, "")}))
    assert any(x.startswith("SOURCE LOW xing") for x in f)
    assert any(x.startswith("SOURCE ZERO linkedin") for x in f)
    assert "BOARD NEW join|new 3 jobs" in f


def test_one_error_is_not_dead(env):
    run(env, BASE, {"ashby|x": (5, "")})
    run(env, BASE, {"ashby|x": (5, "")})
    f = run(env, BASE, {"ashby|x": (0, "HTTP 500")})
    assert not any("BOARD DEAD" in x for x in f)


def test_skipped_source_is_not_zero(env):
    f = run(env, {k: v for k, v in BASE.items() if k != "stepstone"}, BOARDS)
    assert not any("stepstone" in x for x in f)


def test_history_is_capped(env):
    for _ in range(H.KEEP + 3):
        run(env, BASE, BOARDS)
    assert len(json.load(open(H.PATH))["runs"]) == H.KEEP


def test_missing_scratch_files_do_not_crash(env):
    sc = env / "empty"
    sc.mkdir()
    H.main([str(sc)])
    assert json.load(open(H.PATH))["runs"][-1]["candidates"] == 0


def test_render_with_and_without_runs(env):
    assert H.render(str(env)) == 0
    assert "# Radar health" in (env / "reports/HEALTH.md").read_text()
    run(env, BASE, BOARDS)
    last = json.load(open(H.PATH))["runs"][-1]
    (env / "shortlists" / ("%s-%s.json" % (last["date"], last["slot"]))).write_text(
        json.dumps(dict(read_full=40, left_unread=10, minutes=35, jobs=[{}, {}])))
    assert H.render(str(env)) == 1
    md = (env / "reports/HEALTH.md").read_text()
    assert "| 40 | 10 | 35 | 2 |" in md
    assert "greenhouse|dns" in md


def test_latest_flags(env):
    assert H.latest_flags("2026-01-01", "morning") is None


def test_odd_report_and_candidates(env):
    sc = env / "odd"
    sc.mkdir()
    (sc / "ats.json.report").write_text(json.dumps([dict(kind="ashby", slug="x", n=None, err=None), "junk"]))
    (sc / "candidates.json").write_text(json.dumps({"not": "a list"}))
    H.main([str(sc)])
    r = json.load(open(H.PATH))["runs"][-1]
    assert r["boards"] == {"ashby|x": [0, ""]} and r["candidates"] == 0


# 7 Oct 2026: the text check for StepStone, XING and LinkedIn.
def _rows(n_text, n_empty):
    return [dict(url="https://x/%d" % i, desc="x" * 400) for i in range(n_text)] + \
           [dict(url="https://y/%d" % i, desc="") for i in range(n_empty)]


def test_text_empty_flag_at_collection(env):
    sc = env / "sc"
    sc.mkdir()
    (sc / "stepstone.json").write_text(json.dumps(_rows(50, 50)))
    (sc / "xing.json").write_text(json.dumps(_rows(95, 5)))
    (sc / "linkedin.json").write_text(json.dumps(_rows(0, 80)))     # LinkedIn has no text here by design
    stats = H.text_stats(str(sc))
    assert stats["stepstone"] == dict(rows=100, rows_text=50, cand=0, cand_text=0)
    flags = H.text_flags(stats, after_fetch=False)
    assert flags == ["TEXT EMPTY stepstone 50 of 100 collected rows have under 300 characters of text"]


def test_text_check_after_fetch_and_email_line(env):
    sc = env / "sc"
    sc.mkdir()
    (sc / "stepstone.json").write_text(json.dumps(_rows(297, 3)))
    (sc / "linkedin.json").write_text(json.dumps(_rows(0, 80)))
    (sc / "candidates.json").write_text(json.dumps(
        [dict(source="linkedin", desc="x" * 400)] * 6 + [dict(source="linkedin", desc="")] * 4
        + [dict(source="stepstone", desc="short", desc_len=900)] * 5))
    json.dump({"runs": [dict(date="2026-10-07", slot="evening", flags=["SOURCE LOW ba 1 rows"])]}, open(H.PATH, "w"))
    assert H.record_text(str(sc)) == ["TEXT EMPTY linkedin 4 of 10 candidates still have no text after the fetch"]
    rec = H.latest_record("2026-10-07", "evening")
    assert rec["flags"] == ["SOURCE LOW ba 1 rows", "TEXT EMPTY linkedin 4 of 10 candidates still have no text after the fetch"]
    assert H.funnel_lines(rec, [dict(source="linkedin")]) == [
        "StepStone: 300 collected (297 with text), 5 after triage (5 with text), 0 sent",
        "LinkedIn: 80 collected, 10 after triage (6 with text), 1 sent"]
    # A second call replaces the TEXT flags instead of adding them again.
    H.record_text(str(sc))
    assert len([f for f in H.latest_record("2026-10-07", "evening")["flags"] if f.startswith("TEXT")]) == 1


def test_funnel_from_collection_to_sent(env):
    sc = env / "sc"
    sc.mkdir()
    (sc / "stepstone.json").write_text(json.dumps(_rows(202, 0)))
    (sc / "stepstone.log").write_text("TOTAL 548 links, 300 read, 202 within 3 days, 7 detail errors, 0 listing errors []")
    (sc / "candidates.json").write_text(json.dumps([dict(source="stepstone", desc="x" * 400)] * 40))
    H.main([str(sc), "--skipped", ",".join(s for s in H.SOURCES if s != "stepstone")])
    (sc / "candidates.json").write_text(json.dumps([dict(source="stepstone", desc="x" * 400)] * 3))
    H.record_text(str(sc))
    rec = json.load(open(H.PATH))["runs"][-1]
    assert H.funnel_lines(rec, [dict(source="stepstone")]) == [
        "StepStone: 548 links, 300 read, 202 collected (202 with text), 40 after filters, 3 after triage (3 with text), 1 sent"]


def test_dead_and_empty_flags_carry_the_streak_and_return_every_tenth_run(env):
    """29 Oct 2026: three boards stood at 404 for 30 runs behind a flag that said '3 runs running'."""
    boards = {"personio|gone": (0, "HTTP 404"), "ashby|quiet": (0, ""), "ashby|fine": (4, "")}
    seen = {}
    for i in range(1, 21):
        f = run(env, BASE, boards)
        seen[i] = [x for x in f if x.startswith("BOARD")]
    assert seen[1] == [] and seen[2] == []
    assert any(x.startswith("BOARD DEAD personio|gone error 3 runs running") and "COMPANIES.md" in x and "HTTP 404" in x
               for x in seen[3])
    assert any(x == "BOARD EMPTY ashby|quiet 0 jobs 3 runs running" for x in seen[3])
    for i in (4, 5, 9, 11, 19):
        assert seen[i] == [], (i, seen[i])
    assert any("personio|gone error 10 runs running" in x for x in seen[10])
    assert any("ashby|quiet 0 jobs 10 runs running" in x for x in seen[10])
    assert any("personio|gone error 20 runs running" in x for x in seen[20])
    assert not any("ashby|fine" in x for v in seen.values() for x in v)


def test_a_recovery_or_a_new_kind_of_failure_resets_the_streak(env):
    run(env, BASE, {"ashby|x": (0, "HTTP 500")})
    run(env, BASE, {"ashby|x": (0, "HTTP 500")})
    f = run(env, BASE, {"ashby|x": (6, "")})
    assert not any("BOARD" in x for x in f)
    run(env, BASE, {"ashby|x": (0, "HTTP 404")})
    f = run(env, BASE, {"ashby|x": (0, "HTTP 404")})
    assert not any("BOARD DEAD" in x for x in f)
    f = run(env, BASE, {"ashby|x": (0, "dns fail")})
    assert any(x.startswith("BOARD DEAD ashby|x error 3 runs running") for x in f)
    # 0 jobs with an error is dead, 0 jobs without one is empty: the two do not add up.
    run(env, BASE, {"ashby|y": (0, "")})
    run(env, BASE, {"ashby|y": (0, "HTTP 500")})
    f = run(env, BASE, {"ashby|y": (0, "")})
    assert not any("ashby|y" in x for x in f)


def test_a_board_missing_from_a_run_breaks_the_streak(env):
    run(env, BASE, {"ashby|x": (0, "HTTP 404")})
    run(env, BASE, {"ashby|other": (1, "")})
    run(env, BASE, {"ashby|x": (0, "HTTP 404")})
    f = run(env, BASE, {"ashby|x": (0, "HTTP 404")})
    assert not any("BOARD DEAD" in x for x in f)
