"""setup_gen.py renders a filled config/person.md into the profile, the config lists and the salary table."""
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from conftest import ROOT  # noqa: E402
import setup_gen  # noqa: E402
import setup_check  # noqa: E402
import cfg  # noqa: E402

PERSON = """# Person

## Name

Test Person

## Who the candidate is

Machine learning engineer. Berlin, Germany. Non-EU national with a work permit. MSc 2020. 6 years.

## Experience

Civixa, Lahore, ML engineer, 2020 to 2021. Built shelf monitoring with PyTorch.

## Flagship projects

## Tools really used

Python, PyTorch, Docker.

## Target roles

Machine learning engineer first. PhD positions and internships are off.

## Location rules

Berlin, or fully remote from Germany.

## Language level

B1

## Seniority

6 years, mid level and senior, 8+ years out, 3 to 6 years the sweet spot.

## Salary

- startup: EUR 55-60k
- mid: EUR 60-65k
- large:
- public: TV-L E13

## Referral companies

None.

## Referral patterns

- \\bdhl\\b

## Applied before

- Siemens
- TÜV SÜD

## Never send

None yet.

## Search linkedin roles

- machine learning engineer
- AI engineer

## Search linkedin places

- Berlin, Germany

## Search bundesagentur queries

- machine learning

## Search bundesagentur places

- ''

## Search xing queries

- machine learning engineer

## Search xing places

- Berlin

## Search stepstone roles

- machine-learning-engineer

## Search stepstone cities

- berlin

## Search talent roles

- machine learning engineer

## Search talent cities

- Berlin
"""


def make(tmp_path):
    for d in ("config", "instructions", "scripts"):
        (tmp_path / d).mkdir(exist_ok=True)
    shutil.copy(os.path.join(ROOT, "config/radar.yaml"), tmp_path / "config/radar.yaml")
    shutil.copy(os.path.join(ROOT, "instructions/PROFILE.template.md"), tmp_path / "instructions/PROFILE.template.md")
    shutil.copy(os.path.join(ROOT, "scripts/salary.py"), tmp_path / "scripts/salary.py")
    (tmp_path / "config/person.md").write_text(PERSON, encoding="utf-8")
    return tmp_path


def test_a_filled_person_file_makes_the_check_pass(tmp_path, monkeypatch):
    root = make(tmp_path)
    setup_gen.main(str(root))
    profile = (root / "instructions/PROFILE.md").read_text(encoding="utf-8")
    assert "<fill" not in profile
    assert profile.startswith("# Candidate profile — Test Person")
    assert "## Flagship projects" not in profile          # empty answer, section left out
    assert "Older names not in the log: Siemens, TÜV SÜD." in profile
    monkeypatch.setenv("RADAR_CONFIG", str(root / "config/radar.yaml"))
    cfg._cache.clear()
    c = cfg.load()
    assert c["profile"]["name"] == "Test Person"
    assert c["profile"]["referral_companies"] == ["\\bdhl\\b"]
    assert c["profile"]["applied_companies"] == ["siemens", "tüv süd"]
    assert c["search"]["linkedin"]["roles"] == ["machine learning engineer", "AI engineer"]
    assert c["search"]["bundesagentur"]["places"] == [""]
    assert c["search"]["getro"]["collections"][0]["name"] == "Point Nine"   # untouched
    problems = [p for p in setup_check.problems(str(root / "instructions/PROFILE.md"), c) if "salary.py" not in p]
    assert problems == []
    s = (root / "scripts/salary.py").read_text(encoding="utf-8")
    assert '"startup": ("EUR 55-60k",' in s and '"large": ("",' in s and '"public": ("TV-L E13",' in s
    cfg._cache.clear()


def test_running_it_twice_gives_the_same_files(tmp_path):
    root = make(tmp_path)
    setup_gen.main(str(root))
    first = {f: (root / f).read_text(encoding="utf-8") for f in ("instructions/PROFILE.md", "config/radar.yaml", "scripts/salary.py")}
    setup_gen.main(str(root))
    assert {f: (root / f).read_text(encoding="utf-8") for f in first} == first


def test_the_shipped_person_file_is_all_hints(tmp_path):
    person = setup_gen.read_person(os.path.join(ROOT, "config/person.md"))
    assert set(setup_gen.MARKERS) <= set(person)
    for site, keys in setup_gen.SITES.items():
        for k in keys:
            assert "Search %s %s" % (site, k) in person
    assert not [k for k, v in person.items() if v and k != "Salary"], "shipped person.md must carry no answers"
    assert re.sub(r"\s", "", person["Salary"]) == "-startup:-mid:-large:-public:"
