"""Shared setup. Scripts import each other by bare name, so scripts/ goes on the path."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import pytest

LAYOUT = ("state", "reports", "instructions")      # the repo folders since 7 Oct 2026


@pytest.fixture(autouse=True)
def _repo_layout(tmp_path):
    """Many tests use tmp_path, or tmp_path / "repo", as a repo root. Give both the folders."""
    for base in (tmp_path, tmp_path / "repo"):
        for d in LAYOUT:
            (base / d).mkdir(parents=True)
