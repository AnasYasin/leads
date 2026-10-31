"""setup_check.py: the shipped repository is not READY, and a filled profile and config are."""
import os

import setup_check as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FULL = dict(profile=dict(name="Test Person", referral_companies=[], applied_companies=[]),
            search=dict(linkedin=dict(roles=["ml engineer"], places=["Germany"], targets=[]),
                        bundesagentur=dict(queries=["machine learning"], places=[""]),
                        xing=dict(queries=["machine learning"], places=["Berlin"], pages=8),
                        stepstone=dict(roles=["machine-learning-engineer"], cities=["berlin"]),
                        talent=dict(roles=["machine learning engineer"], cities=["Berlin"]),
                        getro=dict(collections=[dict(id=1, name="x")])))


def test_the_shipped_repository_is_not_ready(monkeypatch):
    monkeypatch.setattr(S.salary, "ASK", {"startup": ("", "")})
    out = S.problems()
    assert any("still has a blank" in x for x in out)
    assert "config/radar.yaml profile.name is empty" in out
    assert "config/radar.yaml search.linkedin.roles is empty" in out
    assert any("salary.py" in x for x in out)


def test_a_filled_profile_and_config_are_ready(tmp_path, monkeypatch):
    p = tmp_path / "PROFILE.md"
    p.write_text("# Candidate profile — Test Person\n\n## Who he is\n\nML engineer in Berlin.\n")
    monkeypatch.setattr(S.salary, "ASK", {"startup": ("EUR 50k", "rule")})
    assert S.problems(str(p), FULL) == []
    p.write_text("# Candidate profile — <fill: full name>\n")
    assert S.problems(str(p), FULL) == ["PROFILE.md still has a blank: <fill: full name...>"]
