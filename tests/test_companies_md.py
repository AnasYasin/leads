"""The board list in collect_ats.py and instructions/COMPANIES.md. Importing the collector fetches nothing
since 2 Oct 2026, when the collection moved into main()."""
import os

import pytest

from conftest import ROOT


@pytest.fixture(scope="module")
def ats():
    import collect_ats
    return vars(collect_ats)


def test_every_board_has_a_fetch_url(ats):
    bad = [b for b in ats["BOARDS"] if b[0] not in ats["URLS"]]
    assert bad == []


def test_no_duplicate_boards(ats):
    keys = [(k, s.lower()) for k, s, *_ in ats["BOARDS"]]
    assert len(keys) == len(set(keys))


def test_every_companies_md_board_is_polled(ats):
    # The rule, not particular boards: instructions/PROMPT.md lets a run delete a dead board line.
    import re
    fam = lambda k: k.split("_")[0]
    polled = {(k, s.lower()) for k, s, *_ in ats["BOARDS"]}
    names = {(fam(k), n.split("(")[0].strip().lower()) for k, s, n, *_ in ats["BOARDS"]}
    for line in open(os.path.join(ROOT, "instructions/COMPANIES.md"), encoding="utf-8"):
        m = re.match(r"\s*([a-z_]+)\s*\|\s*([A-Za-z0-9._%\-]+)\s*\|\s*(.+?)\s*\|", line)
        if m and m.group(1) in ats["URLS"]:
            k, slug, name = m.groups()
            assert (k, slug.lower()) in polled or (fam(k), name.split("(")[0].strip().lower()) in names, line[:80]


def test_board_tuples_are_well_formed(ats):
    for b in ats["BOARDS"]:
        assert len(b) >= 3 and all(isinstance(x, str) and x.strip() for x in b[:3]), b


def test_same_board_under_two_kinds_is_polled_once(ats):
    fam = lambda k: k.split("_")[0]
    names = {}
    for k, s, n, *_ in ats["BOARDS"]:
        key = (fam(k), n.split("(")[0].strip().lower())
        names.setdefault(key, []).append((k, s))
    dup = {k: v for k, v in names.items() if len(v) > 1 and len({x[0] for x in v}) > 1}
    assert dup == {}, dup


def test_percent_slug_is_accepted():
    import re
    m = re.match(r"\s*([a-z_]+)\s*\|\s*([A-Za-z0-9._%\-]+)\s*\|\s*(.+?)\s*\|", "ashby | Tools%20for%20Humanity | Tools for Humanity | x")
    assert m and m.group(2) == "Tools%20for%20Humanity"


def test_a_dead_line_retires_the_slug_from_both_lists(ats, tmp_path):
    """29 Oct 2026: Meshcapade's line said 'DEAD, stop polling' since 3 Aug while BOARDS polled it for 30 runs."""
    md = tmp_path / "COMPANIES.md"
    md.write_text("dead | imfusion | ImFusion | gone\n"
                  "personio | fresh-gmbh | Fresh | new board\n"
                  "dead | fresh-gmbh | Fresh | also retired, later line wins nothing: dead is dead\n"
                  "ashby | Keep | Keep | stays\n", encoding="utf-8")
    out, dead = ats["_from_companies_md"](str(md))
    assert dead == {"imfusion", "fresh-gmbh"}
    assert out == [("ashby", "Keep", "Keep")]
    assert not [b for b in ats["BOARDS"] if b[1].lower() in ats["DEAD"]]
    assert "meshcapade" in ats["DEAD"] and not [b for b in ats["BOARDS"] if b[1] == "meshcapade"]


def test_a_missing_companies_md_polls_nothing(ats, tmp_path):
    out, dead = ats["_from_companies_md"](str(tmp_path / "nope.md"))
    assert out == [] and dead == set()
