"""minyaml.py must read what PyYAML reads, or refuse. It must never return something different."""
import os
import random
import sys

import pytest
import yaml

import cfg
import minyaml
from conftest import ROOT

CONFIG = os.path.join(ROOT, "config", "radar.yaml")


def test_the_real_config_reads_the_same():
    text = open(CONFIG, encoding="utf-8").read()
    assert minyaml.loads(text) == yaml.safe_load(text)


def test_cfg_works_without_pyyaml(monkeypatch):
    monkeypatch.setitem(sys.modules, "yaml", None)          # import yaml now raises ImportError
    cfg._cache.clear()
    try:
        assert cfg.load() == yaml.safe_load(open(CONFIG, encoding="utf-8"))
        assert cfg.check() == []
    finally:
        cfg._cache.clear()


CHARS = ("abcxyz ABC 019 äöüß é ñ \\ \\b \\w* (?: ) [ ] { } | ^ $ . * + ? ' \" # : , - & ! % @ ` > < = ~ / "
         "\t\n\u2028 ").split(" ")
WORDS = ["", "no", "No", "on", "OFF", "yes", "true", "null", "~", "3", "-4", "007", "3.5", "1e3", ".inf", "0x1f",
         "2026-09-29", "12:30", "- a", "a: b", "a #b", "#x", "'", '"', "key:", "? x", "=", "<<", "3d", "c#"]


def rand_str(r):
    if r.random() < 0.3:
        return r.choice(WORDS)
    return "".join(r.choice(CHARS) for _ in range(r.randint(1, 12)))


def rand_doc(r, depth=0):
    if depth > 3 or r.random() < 0.3:
        return r.choice([rand_str(r), rand_str(r), r.randint(-50, 5000), r.choice([True, False, None])])
    if r.random() < 0.5:
        return [rand_doc(r, depth + 1) for _ in range(r.randint(0, 4))]
    return {rand_str(r) or "k": rand_doc(r, depth + 1) for _ in range(r.randint(1, 4))}


def test_hostile_generated_files_never_read_differently():
    """Random text full of YAML's special characters. Refusing is allowed; a different result is not."""
    r = random.Random(29092026)
    same = 0
    for _ in range(3000):
        doc = {"top": rand_doc(r)}
        for indent in (2, 4):
            text = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=float("inf"), indent=indent)
            try:
                got = minyaml.loads(text)
            except ValueError:
                continue
            assert got == yaml.safe_load(text), text
            same += 1
    assert same > 1000


def test_config_like_files_are_never_refused():
    """What a person editing radar.yaml writes: patterns from the real file, words, numbers,
    booleans, empty lists and maps. Built from the real config's own values, reshuffled."""
    real = yaml.safe_load(open(CONFIG, encoding="utf-8"))
    pool = []

    def collect(v):
        if isinstance(v, dict):
            for x in v.values():
                collect(x)
        elif isinstance(v, list):
            for x in v:
                collect(x)
        else:
            pool.append(v)
    collect(real)
    r = random.Random(7)
    for _ in range(2000):
        doc = {}
        for k in range(r.randint(1, 5)):
            kind = r.random()
            if kind < 0.5:
                doc["k%d" % k] = r.sample(pool, r.randint(0, 6))
            elif kind < 0.7:
                doc["k%d" % k] = {"s%d" % n: r.choice(pool) for n in range(r.randint(0, 3))}
            elif kind < 0.85:
                doc["k%d" % k] = [{"points": r.randint(-9, 9), "pattern": r.sample(pool, 2)} for _ in range(2)]
            else:
                doc["k%d" % k] = r.choice(pool + [True, False, None, [], {}])
        text = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=float("inf"))
        assert minyaml.loads(text) == yaml.safe_load(text), text


@pytest.mark.parametrize("text,why", [
    ("a: [1, 2]\n", "flow"),
    ("a: {b: 1}\n", "flow"),
    ("- [x]\n", "flow"),
    ("a: &x 1\nb: *x\n", "anchors"),
    ("a: |\n  text\n", "block scalars"),
    ("a: >\n  text\n", "block scalars"),
    ("a: 'wrapped\n  on two lines'\n", "unclosed"),
    ("a: 1.5\n", "quote it"),
    ("a: 2026-09-29\n", "quote it"),
    ("a:\n\t- x\n", "tab"),
    ("a: 1\na: 2\n", "duplicate"),
    ("a:\n  b: 1\n   c: 2\n", "indentation"),
])
def test_what_it_cannot_read_is_refused_with_a_reason(text, why):
    with pytest.raises(ValueError, match=why):
        minyaml.loads(text)


def test_the_forms_the_config_uses():
    text = ("# comment\nprofile:\n  name: the candidate  # trailing comment\n  list:\n  - \\bml\\b\n"
            "  - 'no'\n  - ''\n  - \"c\\u00e4\"\n  nested:\n    - query: DHL AI\n      hours: 168\n"
            "    - query: 'x: y'\n      hours: -1\n  'quoted key': on\n  empty:\n")
    assert minyaml.loads(text) == yaml.safe_load(text)


# Hand-typed values. PyYAML's own writer quotes these, so the generated files above never contain
# them bare; a person editing radar.yaml does (planted-bug check, 29 Sep 2026: reading a bare `no`
# as text went unnoticed until this test).
HAND = ["no", "No", "NO", "yes", "Yes", "on", "On", "off", "OFF", "true", "False", "~", "null", "Null",
        "3", "-4", "+7", "0", "machine learning", "\\bml\\b", "c++", "c#", "C#", "3d", "ki-", "a-b", "x.y",
        "(?:ai|ml)", "ä ö ü", "'quoted'", '"dq"', "'it''s'", "a # comment", "https://x.example/a?b=c"]


@pytest.mark.parametrize("v", HAND)
def test_hand_typed_values_read_like_pyyaml(v):
    for text in ("k: %s\n" % v, "k:\n- %s\n" % v, "k:\n  - %s\n" % v):
        try:
            got = minyaml.loads(text)
        except ValueError:
            continue                  # refusing is allowed; reading it differently is not
        assert got == yaml.safe_load(text), text
