import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from decisions import fingerprint  # noqa: E402
from jobid import sent_match  # noqa: E402

SENT = dict(company="Quantum-Systems", title="Senior Machine Learning Engineer", location="Munich",
            url="https://preply.com/jobs/101", urls=["https://preply.com/jobs/101"], sent="2026-10-30")
TEXT = " ".join("word%d" % i for i in range(60))


def test_nothing_matches():
    assert sent_match("Zalando", "Data Engineer", "Berlin", "https://z.de/j/1", "", [SENT]) == (None, False)


def test_a_repeat_by_title_and_by_link():
    m, so = sent_match("Quantum-Systems", "Senior Machine Learning Engineer", "Munich", "https://preply.com/jobs/999", "", [SENT])
    assert m is SENT and so is False
    m, so = sent_match("", "Something else", "", "https://preply.com/jobs/101?utm_source=x", "", [SENT])
    assert m is SENT and so is False


def test_a_second_opening_needs_both_links_live_in_the_pool():
    row = ("Quantum-Systems", "Senior Robotics & Machine Learning Engineer", "Munich", "https://preply.com/jobs/202", "", [SENT])
    assert sent_match(*row, pool_urls={"https://preply.com/jobs/101", "https://preply.com/jobs/202"}) == (SENT, True)
    assert sent_match(*row, pool_urls=set()) == (SENT, False)


def test_the_fallback_link_counts_for_a_second_opening():
    pool = {"https://preply.com/jobs/101", "https://preply.com/jobs/202"}
    m, so = sent_match("Quantum-Systems", "Senior Robotics & Machine Learning Engineer", "Munich", "", "", [SENT], pool_urls=pool,
                       links=["https://preply.com/jobs/202"])
    assert (m, so) == (SENT, True)


def test_a_text_twin_under_another_company_name_is_a_repeat():
    prints = [(SENT, fingerprint(TEXT))]
    m, so = sent_match("Mitsui Chemicals", "Senior Machine Learning Engineer", "Berlin", "https://m.jp/1", TEXT, [], prints=prints)
    assert m is SENT and so is False
    m, so = sent_match("Mitsui Chemicals", "Senior Machine Learning Engineer", "Berlin", "https://m.jp/1", "other text", [], prints=prints)
    assert (m, so) == (None, False)


def test_a_second_opening_that_is_a_twin_of_another_sent_job_is_a_repeat_of_that_one():
    other = dict(company="Rohlik", title="Senior Robotics & Machine Learning Engineer", url="https://rohlik.cz/j/7", sent="2026-10-29")
    pool = {"https://preply.com/jobs/101", "https://preply.com/jobs/202"}
    m, so = sent_match("Quantum-Systems", "Senior Robotics & Machine Learning Engineer", "Munich", "https://preply.com/jobs/202", TEXT, [SENT],
                       pool_urls=pool, prints=[(other, fingerprint(TEXT))])
    assert m is other and so is False
