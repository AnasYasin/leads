"""Every script imports. Added 1 Nov 2026 after pipeline.py had failed at import for a day: a module
named like one of its own functions, and no test imported the module. Five scripts read their command
line at module level and are run, never imported, so they are compiled only."""
import glob
import os
import subprocess
import sys

from conftest import SCRIPTS

RUN_ONLY = {"collect_all", "collect_arbeitnow", "collect_ba", "collect_talent", "filter_run"}


def test_every_script_imports_or_compiles():
    bad = []
    for path in sorted(glob.glob(os.path.join(SCRIPTS, "*.py"))):
        name = os.path.basename(path)[:-3]
        if name in RUN_ONLY:
            code = "import py_compile, sys; py_compile.compile(sys.argv[1], doraise=True)"
            args = [sys.executable, "-c", code, path]
        else:
            args = [sys.executable, "-c", "import sys; sys.argv = ['x']; import %s" % name]
        p = subprocess.run(args, cwd=SCRIPTS, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            bad.append("%s: %s" % (name, (p.stderr.strip().splitlines() or ["?"])[-1]))
    assert not bad, "\n".join(bad)
