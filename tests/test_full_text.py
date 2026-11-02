"""No description is cut anywhere between the source and candidates.json (docs/PROBLEMS.md 1.1, 1.2, 1.9).

Until 2 Oct 2026 filter_run.py cut every inline description at 6,000 characters, the collectors at
12,000 and one reader at 9,000. The cut took the end of the posting, where the language line and
the requirements usually sit: of 36 cut rows checked on 30 Sep, 3 lost a German requirement
(BLP Digital, Doctolib, Celonis) and 2 lost the whole requirements section (Makersite, SumUp)."""
import glob
import json
import os
import re
import subprocess
import sys

from conftest import SCRIPTS

SENTENCE = "You train and ship PyTorch models for computer vision and you own the evaluation. "


def run_filter(tmp_path, source_file, row):
    sc = tmp_path / "sc"
    sc.mkdir()
    for src in ("ba", "ats", "getro", "talent", "arbeitnow", "linkedin", "xing", "stepstone"):
        (sc / (src + ".json")).write_text("[]")
    (sc / (source_file + ".json")).write_text(json.dumps([row]))
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "filter_run.py"), str(sc)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-2000:]
    return sc


def long_row(tail, **kw):
    return dict(company="Zz Test Co", title="Machine Learning Engineer", location="Berlin, Germany",
                url="https://zz.example/1", date="2099-01-01", desc=SENTENCE * 400 + tail, **kw)


def test_a_long_description_reaches_the_candidates_whole(tmp_path):
    tail = "Our working language is English."
    for src, extra in (("ats", dict(source="greenhouse")), ("arbeitnow", {}), ("xing", {}), ("stepstone", {})):
        d = tmp_path / src
        d.mkdir()
        sc = run_filter(d, src, long_row(tail, **extra))
        got = json.load(open(sc / "candidates.json"))
        assert len(got) == 1, src
        assert len(got[0]["desc"]) > 30000 and got[0]["desc"].endswith(tail), src


def test_a_german_line_at_the_very_end_is_seen(tmp_path):
    # 32,000 characters in, far beyond the old cut. The row must leave on German, not be sent unread.
    sc = run_filter(tmp_path, "ats", long_row("Fluent German is required.", source="greenhouse"))
    assert json.load(open(sc / "candidates.json")) == []
    off = json.load(open(sc / "german_off.json"))
    assert len(off) == 1 and off[0]["line"] == "Fluent German is required."


def test_no_script_slices_a_description():
    # A description is never shortened by a slice. This catches a new `desc[:6000]` before it ships.
    bad = []
    rx = re.compile(r"""desc["')\]\s]*(?:\s+or\s+["']{2}\))?\[:\s*\d{3,}\]|desc["'\]]*\s*[:=]\s*.*\)\[:\s*\d{4,}\]""")
    for f in sorted(glob.glob(os.path.join(SCRIPTS, "*.py"))):
        for n, line in enumerate(open(f, encoding="utf-8"), 1):
            if rx.search(line) and not line.lstrip().startswith("#"):
                bad.append("%s:%d %s" % (os.path.basename(f), n, line.strip()[:90]))
    assert bad == []
