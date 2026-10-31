import json

import pytest

import fetch_desc as F

# Longer than fetch_desc.THIN: a shorter text counts as "no text" since 2 Oct 2026.
PLAIN = " ".join(["You build PyTorch models for computer vision and deploy them with Docker."] * 5)
GERMAN = PLAIN + " Wir erwarten sehr gute Deutschkenntnisse (C1) in Wort und Schrift."


@pytest.fixture
def sc(tmp_path):
    rows = [dict(company="A", title="ML Engineer", source="ats", desc=PLAIN),
            dict(company="B", title="KI Entwickler", source="Bundesagentur", ref="b1"),
            dict(company="C", title="Data Scientist", source="Bundesagentur", ref="c1"),
            dict(company="D", title="AI Engineer", source="linkedin", li_id="d1"),
            dict(company="E", title="ML Engineer", source="talent.com", url="e"),
            dict(company="F", title="CV Engineer", source="Bundesagentur", ref="f1", referral=True)]
    (tmp_path / "candidates.json").write_text(json.dumps(rows))
    return tmp_path


def fake(texts):
    def fn(j):
        out = dict(j)
        v = texts[j["company"]]
        if isinstance(v, Exception):
            out["error"] = str(v)
        else:
            out["desc"] = v
            out["employer_site"] = "https://%s.example" % j["company"].lower()
        return out
    return fn


def load(sc):
    return {r["company"]: r for r in json.load(open(sc / "candidates.json"))}


def test_fetches_drops_german_and_keeps_failures(sc):
    texts = {"B": GERMAN, "C": PLAIN, "D": RuntimeError("HTTP 429"), "E": "FETCH FAILED: timeout", "F": GERMAN}
    s = F.run(str(sc), {"Bundesagentur": fake(texts), "linkedin": fake(texts), "talent.com": fake(texts)})
    rows = load(sc)
    assert "B" not in rows                               # German requirement, dropped
    assert rows["C"]["desc"] and rows["C"]["desc_fetched"]
    assert rows["C"]["employer_site"] == "https://c.example"
    assert not rows["D"].get("desc") and not rows["E"].get("desc")   # failed fetches stay, unread
    assert "F" in rows                                   # referral rows are never dropped on German
    assert rows["A"]["desc"] == PLAIN                    # rows that had a description are untouched
    assert s == dict(asked=5, fetched=3, failed=2, gone=0, german=1, clearance=0, repeats=0, left=5,
                     by_source={"Bundesagentur": [3, 3], "linkedin": [1, 0], "talent.com": [1, 0]})
    no = json.load(open(sc / "no_text.json"))
    assert {n["job"] for n in no} == {"D | AI Engineer", "E | ML Engineer"} and "429" in no[0]["why"] + no[1]["why"]
    off = json.load(open(sc / "german_off_fetched.json"))
    assert off[0]["job"] == "B | KI Entwickler" and "Deutschkenntnisse" in off[0]["line"]


def test_rows_are_sorted_by_prescore_after_fetch(sc):
    texts = {k: PLAIN for k in "BCDEF"}
    F.run(str(sc), {"Bundesagentur": fake(texts), "linkedin": fake(texts), "talent.com": fake(texts)})
    rows = json.load(open(sc / "candidates.json"))
    scores = [r["prescore"] for r in rows]
    assert scores == sorted(scores, reverse=True)


def test_sources_without_a_fetcher_are_left_alone(sc):
    s = F.run(str(sc), {"talent.com": fake({"E": PLAIN})})
    rows = load(sc)
    assert s["asked"] == 1 and rows["E"]["desc"] and not rows["B"].get("desc")


def test_readers_import_without_a_command_line():
    r = F.readers()
    assert set(r) == {"Bundesagentur", "linkedin", "talent.com", "*"} and all(callable(f) for f in r.values())


LONG = PLAIN * 6


def test_rows_from_any_source_without_text_are_fetched(tmp_path):
    # 2 Oct 2026: Getro and the card-only boards (SmartRecruiters, JOIN, Avature, Breezy) had no reader.
    rows = [dict(company="G", title="ML Engineer", source="getro:HV Capital", url="g"),
            dict(company="S", title="Data Scientist", source="ATS/ats:smartrecruiters", url="s", desc=""),
            dict(company="P", title="AI Engineer", source="ATS/ats:personio", url="p", desc="2811392 Berlin permanent"),
            dict(company="X", title="CV Engineer", source="getro:Earlybird", url="x"),
            dict(company="C", title="NLP Engineer", source="getro:Point Nine", url="c"),
            dict(company="K", title="ML Engineer", source="xing", url="k", desc=LONG)]
    (tmp_path / "candidates.json").write_text(json.dumps(rows))
    texts = {"G": LONG, "S": LONG + " " + GERMAN, "P": LONG, "X": RuntimeError("HTTP 403, the site blocks scripts")}

    def page(j):
        if j["company"] == "C":
            return dict(j, error="gone: the Ashby posting is closed", gone=True)
        r = fake(texts)(j)
        return dict(r, desc_src="json-ld") if r.get("desc") else r
    s = F.run(str(tmp_path), {"*": page})
    got = load(tmp_path)
    assert got["G"]["desc"] and got["G"]["desc_src"] == "json-ld" and got["G"]["desc_len"] == len(LONG)
    assert got["P"]["desc"].startswith("You build")          # feed metadata replaced by the posting
    assert "S" not in got and "C" not in got                 # German after the full text, and a closed posting
    assert not got["X"].get("desc") and got["K"]["desc"] == LONG
    assert s["asked"] == 5 and s["fetched"] == 3 and s["failed"] == 1 and s["gone"] == 1 and s["german"] == 1
    assert s["by_source"] == {"getro": [3, 1], "boards": [2, 2]}
    assert json.load(open(tmp_path / "gone.json"))[0]["job"] == "C | NLP Engineer"
    assert json.load(open(tmp_path / "no_text.json"))[0]["why"].startswith("HTTP 403")
    assert "5 candidates" not in F.report(str(tmp_path)) and "4 candidates, 3 with the full text, 1 without text" in F.report(str(tmp_path))


def test_a_thin_source_text_is_replaced_from_the_employer_link(tmp_path):
    # A BA row that says "siehe Homepage" and carries the employer's link.
    rows = [dict(company="B", title="KI Entwickler", source="Bundesagentur", ref="b1")]
    (tmp_path / "candidates.json").write_text(json.dumps(rows))

    def ba(j):
        return dict(j, desc="Siehe Homepage.", externe_url="https://b.example/job")

    def page(j):
        assert j["externe_url"] == "https://b.example/job"
        return dict(j, desc=LONG, desc_src="page")
    s = F.run(str(tmp_path), {"Bundesagentur": ba, "*": page})
    got = load(tmp_path)["B"]
    assert got["desc"] == LONG and got["desc_src"] == "page" and got["externe_url"] == "https://b.example/job"
    assert s["fetched"] == 1 and s["failed"] == 0


def test_nothing_is_cut_at_any_length(tmp_path):
    big = (PLAIN + " ") * 2000 + "German C1 is required."
    (tmp_path / "candidates.json").write_text(json.dumps([dict(company="L", title="ML Engineer", source="getro:x", url="l", referral=True)]))
    F.run(str(tmp_path), {"*": lambda j: dict(j, desc=big, desc_src="page")})
    got = load(tmp_path)["L"]
    assert len(got["desc"]) == len(big) > 140000 and got["desc"].endswith("German C1 is required.")
