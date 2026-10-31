"""config/radar.yaml, the loader, and the scripts that read it.

tests/data/config_golden.json holds every constant as it was hardcoded before 29 Sep 2026, read
out of the old source with ast. The first tests prove the move to YAML changed no pattern and no
search term. The rest cover the loader's edge cases and prove a different profile really
changes what the filter keeps.
"""
import importlib
import json
import os
import re
import subprocess
import sys

import pytest
import yaml

import cfg
from conftest import ROOT, SCRIPTS

GOLDEN = json.load(open(os.path.join(ROOT, "tests", "data", "config_golden.json"), encoding="utf-8"))
CONFIG = os.path.join(ROOT, "config", "radar.yaml")

FILTERS = {"GOOD": ("filters", "title_good"), "BAD": ("filters", "title_bad"),
           "NOTWANTED": ("filters", "not_wanted"), "DATA_FAMILY": ("filters", "data_family"),
           "CORE_ML": ("filters", "core_ml"), "SENIOR_OUT": ("filters", "senior_out"),
           "JUNK_EMPLOYER": ("filters", "junk_employer"), "RECRUITER": ("filters", "recruiter"),
           "PHD_OFF": ("filters", "phd_off"),
           "DE_HINT": ("filters", "location_ok"), "OUT_OF_SCOPE": ("filters", "location_out"),
           "ANYWHERE": ("filters", "location_anywhere"), "TITLE_NOISE_DROP": ("filters", "title_noise_drop"),
           "TITLE_FIELD": ("filters", "title_field")}


@pytest.fixture(autouse=True)
def default_config(monkeypatch):
    monkeypatch.delenv("RADAR_CONFIG", raising=False)
    cfg._cache.clear()
    yield
    cfg._cache.clear()


# --- the move changed nothing ---------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(FILTERS))
def test_filter_pattern_is_the_old_hardcoded_one(name):
    assert cfg.pattern(cfg.get(*FILTERS[name])) == GOLDEN["filter_run"][name]["pattern"]
    assert cfg.rx(*FILTERS[name]).flags & re.I



def test_prescore_terms_and_weights_are_the_old_ones():
    import prescore
    old = GOLDEN["prescore"]
    assert prescore.ML_WORD == old["ML_WORD"]
    assert prescore.T_SPECIFIC == old["T_SPECIFIC"] and prescore.T_GENERIC == old["T_GENERIC"]
    assert [list(x) for x in prescore.T_PLUS] == old["T_PLUS"]
    assert [list(x) for x in prescore.T_MINUS] == old["T_MINUS"]
    assert prescore.D_PLUS == old["D_PLUS"] and prescore.INFRA == old["INFRA"]
    assert [list(x) for x in prescore.D_MINUS] == old["D_MINUS"]


def test_structured_search_lists_are_the_old_ones():
    # Public copy: the person's own queries and places are filled at setup (SETUP.md); only the shipped
    # Getro collections are pinned here.
    assert [[c["id"], c["name"]] for c in cfg.get("search", "getro", "collections")] == GOLDEN["collect_getro"]["COLLECTIONS"]


def test_prescore_scores_are_unchanged_on_fixed_rows():
    """Scores and reasons below were printed by the pre-refactor prescore.py (git 25d8222) on 29 Sep 2026."""
    import datetime
    import prescore
    today = datetime.date(2026, 9, 29)
    rows = [
        (dict(title="Computer Vision Engineer", company="X", source="linkedin", location="Berlin", date="2026-09-29"),
         10, ["+4 computer vision", "+1 no desc", "+2 age 0d", "+2 linkedin", "+1 berlin"]),
        (dict(title="Staff Machine Learning Engineer", company="X", desc="pytorch fsdp slurm deepspeed", date="2026-09-01"),
         -5, ["+3 machine learning", "-5 staff", "+1 desc", "-3 infra core (3)", "-1 age 28d"]),
        (dict(title="Werkstudent Data Analyst", company="X", source="ats", date="2026-08-01"),
         -9, ["-4 werkstudent", "-4 data analyst", "-1 age 59d"]),
        (dict(title="Director Information Security, DHL Data & AI", company="DHL Data & AI", referral=True),
         -5, ["-5 director"]),
        (dict(title="Data Scientist", company="DHL", referral=True, desc="python"),
         11, ["+1 data scientist", "+10 referral"]),
    ]
    for j, want, want_why in rows:
        assert prescore.score(j, today, no_desc=1) == (want, want_why), j["title"]


# --- every key a script asks for exists --------------------------------------------------------

CALL = re.compile(r"cfg\.(?:get|rx)\(((?:\s*\"[^\"]+\"\s*,?)+)\)")


def test_every_config_path_in_the_scripts_exists():
    seen = 0
    for f in os.listdir(SCRIPTS):
        if not f.endswith(".py") or f == "cfg.py":
            continue
        for m in CALL.finditer(open(os.path.join(SCRIPTS, f), encoding="utf-8").read()):
            keys = re.findall(r'"([^"]+)"', m.group(1))
            cfg.get(*keys)          # KeyError names the missing path
            seen += 1
    assert seen >= 20


def test_every_prescore_key_the_code_reads_exists():
    src = open(os.path.join(SCRIPTS, "prescore.py"), encoding="utf-8").read()
    keys = set(re.findall(r'P\["([a-z_]+)"\]', src))
    assert keys and keys <= set(cfg.get("prescore")), keys - set(cfg.get("prescore"))


def test_the_shipped_file_passes_its_own_check():
    assert cfg.check() == []


# --- loader edge cases ------------------------------------------------------------------------

def write(tmp_path, data, name="radar.yaml"):
    p = tmp_path / name
    p.write_text(data if isinstance(data, str) else yaml.safe_dump(data, allow_unicode=True))
    return str(p)


@pytest.mark.parametrize("value", [[], None, "", ["", None]])
def test_an_empty_pattern_matches_nothing(value):
    rx = re.compile(cfg.pattern(value), re.I)
    assert not rx.search("Machine Learning Engineer") and not rx.search("")


def test_blank_entries_inside_a_list_are_skipped():
    assert cfg.pattern(["a", "", None, "b"]) == "a|b"


def test_a_yaml_boolean_in_a_pattern_list_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_CONFIG", write(tmp_path, "filters:\n  title_bad:\n  - sales\n  - no\n"))
    with pytest.raises(ValueError, match="quote it"):
        cfg.rx("filters", "title_bad")


def test_a_number_in_a_pattern_list_is_text(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_CONFIG", write(tmp_path, "filters:\n  title_good:\n  - 3d\n  - 2024\n"))
    assert cfg.rx("filters", "title_good").search("Senior 2024 role")


def test_a_missing_key_names_the_path(monkeypatch, tmp_path):
    monkeypatch.setenv("RADAR_CONFIG", write(tmp_path, {"filters": {}}))
    with pytest.raises(KeyError, match="filters.title_good"):
        cfg.get("filters", "title_good")


def test_broken_yaml_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setenv("RADAR_CONFIG", write(tmp_path, "filters:\n  title_good: [unclosed\n"))
    with pytest.raises(yaml.YAMLError):
        cfg.load()


def test_a_missing_file_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setenv("RADAR_CONFIG", str(tmp_path / "nope.yaml"))
    with pytest.raises(FileNotFoundError):
        cfg.load()


def test_check_reports_a_bad_regex(monkeypatch, tmp_path):
    data = yaml.safe_load(open(CONFIG, encoding="utf-8"))
    data["filters"]["title_bad"].append("unclosed(group")
    monkeypatch.setenv("RADAR_CONFIG", write(tmp_path, data))
    assert any(p.startswith("filters.title_bad") for p in cfg.check())


def test_special_characters_survive_the_file(monkeypatch, tmp_path):
    tricky = [r"\bml\b", "künstliche intelligenz", "c#", r"a: b", "# not a comment", r"\.net", "'quoted'", "x{2,3}"]
    monkeypatch.setenv("RADAR_CONFIG", write(tmp_path, {"filters": {"title_good": tricky}}))
    assert cfg.get("filters", "title_good") == tricky
    rx = cfg.rx("filters", "title_good")
    assert rx.search("Künstliche Intelligenz Entwickler") and rx.search("C# developer") and rx.search("Senior ML role")


def test_the_config_can_live_anywhere_and_cwd_does_not_matter(tmp_path):
    out = subprocess.run([sys.executable, os.path.join(SCRIPTS, "cfg.py")], cwd=str(tmp_path),
                         capture_output=True, text=True)
    assert out.returncode == 0 and "every pattern compiles" in out.stdout


# --- a different profile really changes the result -----------------------------------------

def other_profile(tmp_path):
    """The same file, pointed at a frontend developer in Vienna."""
    data = yaml.safe_load(open(CONFIG, encoding="utf-8"))
    data["profile"]["referral_companies"] = []
    data["profile"]["applied_companies"] = []
    f = data["filters"]
    f["title_good"] = ["frontend", "react", "vue"]
    f["title_bad"] = ["sales"]
    f["not_wanted"] = ["backend"]
    f["not_wanted_unless_ai"] = []
    f["senior_out"] = []
    f["location_ok"] = ["vienna", "wien", "austria"]
    f["location_out"] = ["berlin", "germany"]
    return write(tmp_path, data)


def test_another_profile_keeps_other_jobs(tmp_path):
    sc = tmp_path / "sc"
    sc.mkdir()
    rows = [dict(company="Acme Web", title="Senior Frontend Developer (React)", location="Vienna, Austria",
                 url="https://acme.example/1", date="2026-09-29", desc="React and TypeScript."),
            dict(company="Acme ML", title="Machine Learning Engineer", location="Berlin, Germany",
                 url="https://acme.example/2", date="2026-09-29", desc="PyTorch."),
            dict(company="Acme Web", title="Backend Developer", location="Vienna",
                 url="https://acme.example/3", date="2026-09-29", desc="Go.")]
    for src in ("ba", "getro", "talent", "arbeitnow", "linkedin", "xing", "stepstone"):
        (sc / (src + ".json")).write_text("[]")

    def kept(env_config):
        (sc / "ats.json").write_text(json.dumps([dict(r, board="x", kind="greenhouse") for r in rows]))
        env = dict(os.environ)
        env.pop("RADAR_CONFIG", None)
        if env_config:
            env["RADAR_CONFIG"] = env_config
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "filter_run.py"), str(sc)],
                           capture_output=True, text=True, env=env)
        assert p.returncode == 0, p.stderr[-2000:]
        return sorted(c["title"] for c in json.load(open(sc / "candidates.json")))

    assert kept(None) == ["Machine Learning Engineer"]
    assert kept(other_profile(tmp_path)) == ["Senior Frontend Developer (React)"]


def test_another_profile_changes_the_read_order(tmp_path, monkeypatch):
    data = yaml.safe_load(open(CONFIG, encoding="utf-8"))
    data["prescore"]["title_specific"] = ["frontend"]
    data["prescore"]["source_bonus"] = {"xing": 5}
    monkeypatch.setenv("RADAR_CONFIG", write(tmp_path, data))
    cfg._cache.clear()
    import prescore
    prescore = importlib.reload(prescore)
    try:
        s, why = prescore.score(dict(title="Frontend Developer", company="X", source="xing"), no_desc=0)
        assert "+4 frontend" in why and "+5 xing" in why
    finally:
        monkeypatch.delenv("RADAR_CONFIG")
        cfg._cache.clear()
        importlib.reload(prescore)
