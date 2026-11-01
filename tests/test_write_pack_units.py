"""enrich() and email_md() on plain dicts, no repo copy, no subprocess (1 Nov 2026 split of main)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import write_pack as W  # noqa: E402


def job(**kw):
    base = dict(company="Testfirma GmbH", title="Computer Vision Engineer", location="Berlin", fit=8, priority=10,
                band="A", apply_url="https://example.org/job/1", desc="We build PyTorch detection models.")
    base.update(kw)
    return base


def test_enrich_drops_gone_jobs_and_reads_the_salary(monkeypatch):
    monkeypatch.setattr(W, "live", lambda u: ("GONE", "404") if u.endswith("/2") else ("LIVE", "200"))
    monkeypatch.setattr(W, "true_date", lambda u, t="": (None, ""))
    monkeypatch.setattr(W.company_cache, "get", lambda c: {})
    a = job(desc="Gehalt 70.000 bis 80.000 EUR pro Jahr. PyTorch.")
    b = job(apply_url="https://example.org/job/2")
    jobs, dropped = W.enrich([a, b], "2026-11-01")
    assert jobs == [a] and dropped == [b]
    assert a["_live"].startswith("LIVE") and a["salary"]


def test_enrich_recomputes_priority_from_bonus(monkeypatch):
    monkeypatch.setattr(W, "live", lambda u: ("LIVE", "200"))
    monkeypatch.setattr(W, "true_date", lambda u, t="": (None, ""))
    monkeypatch.setattr(W.company_cache, "get", lambda c: {})
    j = job(fit=7, bonus=1, posted="2026-11-01", priority=99)
    W.enrich([j], "2026-11-01")
    assert j["priority"] == 7 + W.freshness("2026-11-01", "2026-11-01") + 1


def test_email_md_lists_every_section(tmp_path):
    sl = dict(date="2026-11-01", slot="morning", coverage=[], notes="a note",
              borderline=[dict(company="B Co", title="ML Engineer", fit=6, reason="close")],
              also_found=[dict(company="C Co", title="Data Scientist", location="Berlin", fit=6, band="A", url="https://c.example")],
              direct_look=[dict(company="D Co", what="worth a look", url="https://d.example")],
              rejected=[dict(company="E Co", title="Analyst", fit=3, gate="field", reason="not ML")])
    j = job(_pack="jobs/x.md", _live="LIVE (200)")
    md = W.email_md(sl, [j], [], str(tmp_path), None, "2026-11-01", "morning")
    for line in ("# Job radar, 2026-11-01 morning, 1 new", "## Borderline, not sent (1)", "## Fit 6, one line each (1)",
                 "## Companies worth a direct look", "## Rejected", "a note", "Testfirma GmbH"):
        assert line in md, line
