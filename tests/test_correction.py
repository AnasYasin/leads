import json
import os
import shutil
import subprocess

from conftest import ROOT


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)


def test_first_send_is_normal_and_rerender_lists_only_changes(tmp_path):
    (tmp_path / "scripts").mkdir()
    shutil.copy(os.path.join(ROOT, "scripts", "correction.py"), tmp_path / "scripts")
    (tmp_path / "shortlists").mkdir()
    run(["git", "init", "-q"], tmp_path)
    run(["git", "config", "user.email", "t@t"], tmp_path)
    run(["git", "config", "user.name", "t"], tmp_path)
    md, js = tmp_path / "shortlists" / "2026-09-29-morning.md", tmp_path / "shortlists" / "2026-09-29-morning.json"
    job = lambda c, t: dict(company=c, title=t, location="Berlin", fit=7, apply_url="https://x/" + c)
    md.write_text("# Job radar, 7 new\n")
    js.write_text(json.dumps(dict(jobs=[job("A", "ML Engineer"), job("B", "CV Engineer")])))
    run(["git", "add", "-A"], tmp_path)
    run(["git", "commit", "-qm", "first"], tmp_path)
    first = run(["python3", "scripts/correction.py", str(md)], tmp_path).stdout.strip()
    assert first == ""
    md.write_text("# Job radar, 9 new\n")
    js.write_text(json.dumps(dict(jobs=[job("A", "ML Engineer"), job("C", "AI Engineer")])))
    run(["git", "add", "-A"], tmp_path)
    run(["git", "commit", "-qm", "second"], tmp_path)
    env = dict(os.environ, RUNNER_TEMP=str(tmp_path))
    out = subprocess.run(["python3", "scripts/correction.py", str(md)], cwd=tmp_path, capture_output=True, text=True, env=env).stdout.strip()
    text = open(out).read()
    assert text.startswith("# Correction:") and "Added (1)" in text and "C" in text and "Removed (1)" in text
    assert "ML Engineer — A" not in text
