#!/usr/bin/env python3
"""The radar's configuration, read from config/radar.yaml. Added 29 Sep 2026.

Every profile fact, search term, title filter and ranking weight used to be hardcoded in the
scripts. They now live in config/radar.yaml, so the radar can be pointed at another person or
another kind of job without touching code. RADAR_CONFIG=<path> points at another file (tests).

    import cfg
    cfg.get("search", "linkedin", "roles")     a value, or KeyError naming the missing path
    cfg.rx("filters", "title_good")            a compiled, case-insensitive pattern
    python3 scripts/cfg.py                     check the file loads and every pattern compiles
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_cache = {}


def _parse(text):
    """PyYAML when it is installed, else the small reader in minyaml.py. Both give the same result
    on this file (tests/test_minyaml.py). The fallback replaced a pip install per process, which
    could fail when the collectors started at once (review, 29 Sep 2026)."""
    try:
        import yaml
    except ImportError:
        import minyaml
        return minyaml.loads(text)
    return yaml.safe_load(text)


def path():
    return os.environ.get("RADAR_CONFIG") or os.path.join(ROOT, "config", "radar.yaml")


def load():
    p = path()
    if p not in _cache:
        _cache[p] = _parse(open(p, encoding="utf-8").read())
    return _cache[p]


def get(*keys):
    v = load()
    for i, k in enumerate(keys):
        if not isinstance(v, dict) or k not in v:
            raise KeyError("config/radar.yaml has no %s" % ".".join(keys[:i + 1]))
        v = v[k]
    return v


NEVER = r"(?!)"      # matches nothing


def pattern(v):
    """A list of alternatives joined with |, or a single pattern string.

    An empty list, an empty string or a missing value (`title_bad:` with nothing after it) matches
    nothing. Joined as is it would be the empty pattern, which matches every title, so emptying a
    block list would drop every job. Blank entries inside a list are skipped for the same reason."""
    if v is None:
        return NEVER
    # YAML reads a bare yes, no, on, off, true or false as a boolean. As a pattern that would
    # silently become "True". Quote such words in the file ('no').
    for x in (v if isinstance(v, list) else [v]):
        if isinstance(x, bool):
            raise ValueError("config/radar.yaml: a pattern reads as %s; quote it, as in '%s'"
                             % (x, "yes" if x else "no"))
    if isinstance(v, list):
        parts = [str(x) for x in v if x is not None and str(x) != ""]
        return "|".join(parts) if parts else NEVER
    return str(v) if str(v) != "" else NEVER


def patterns(v):
    """A list of separate patterns (each one tested on its own, as prescore's desc_plus and infra
    are). Blank entries are dropped and a YAML boolean is refused, as in pattern()."""
    items = v if isinstance(v, list) else ([] if v is None else [v])
    for x in items:
        if isinstance(x, bool):
            pattern([x])                     # raises the same "quote it" error
    return [str(x) for x in items if x is not None and str(x) != ""]


def rx(*keys, flags=re.I):
    return re.compile(pattern(get(*keys)), flags)


def _walk(v, where):
    if isinstance(v, dict):
        for k, x in v.items():
            yield from _walk(x, where + (k,))
    elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
        for i, x in enumerate(v):
            yield from _walk(x, where + (str(i),))
    else:
        yield where, v


def check():
    """Compile every pattern in profile, filters and prescore, one by one and joined.
    Returns a list of problems, empty when the file is sound."""
    bad = []
    for sec in ("profile", "filters", "prescore"):
        for where, v in _walk(get(sec), (sec,)):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                continue
            if where[-1] in ("name", "guide", "applied_companies"):   # plain text, not patterns
                continue
            items = v if isinstance(v, list) else [v]
            try:
                for s in items + [pattern(v)]:
                    if not isinstance(s, (str, type(None))):
                        raise ValueError("not text: %r" % (s,))
                    re.compile(pattern(s), re.I)
            except (re.error, ValueError) as ex:
                bad.append("%s: %s" % (".".join(where), ex))
    return bad


if __name__ == "__main__":
    problems = check()
    print("%s: %s" % (path(), "ok, every pattern compiles" if not problems else "%d problems" % len(problems)))
    for p in problems:
        print("  " + p)
    sys.exit(1 if problems else 0)
