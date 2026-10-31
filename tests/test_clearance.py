"""scripts/clearance.py: nationality and security-clearance lines (docs/PROBLEMS.md 3.6, the candidate's decision of 2 Oct 2026).
Every line is from a real posting or from a past rejection."""
import pytest

from clearance import check

DROP = [
    # nationality, always a drop
    "Must be a citizen of a NATO member state (due to export control and security regulations).",          # STARK
    "NATO Citizenship: Must be a citizen of a NATO member state (due to export control and security regulations).",
    "Nur Bewerber aus NATO und EU Mitglieds-Staaten können akzeptiert werden",                               # encontec
    "For international applicants: Please note that only applicants from NATO and EU member states can be accepted",
    "Nationality of a NATO member nation or close ally is required",                                          # Autonomous Teaming, sent 30 Sep and 2 Oct
    "NATO-aligned nationality or close ally citizenship is required",
    "Onsite work in Berlin and NATO member state citizenship are mandatory",
    "Mandatory citizenship of a NATO member state",
    "Eligibility: must hold citizenship in the target territory (France for now)",                           # Mistral AI
    "U.S. citizenship is required to access classified information.",                                        # Databricks
    "Deutsche Staatsangehörigkeit erforderlich",
    "EU-Staatsbürgerschaft ist zwingend erforderlich.",
    # a firm clearance requirement
    "Due to the nature of the role, eligibility for a security clearance is required.",                      # Quantum-Systems
    "Hold, or are willing and able to obtain, an extended German security clearance (erweiterte Sicherheitsüberprüfung, Ü2 or Ü3)",
    "Given the nature of SE3's work in the defence sector, candidates must be eligible to obtain and hold the security clearance required for this role.",
    "MUST be eligible for UK Security Clearance and be able to travel to the South West England area when required",
    "Eligibility for UK Security Check (SC) clearance is required; existing clearance is a strong advantage.",
    "This role will require an active TS security clearance",
    "Required: Top Secret clearance with eligibility for SCI",
    "Bereitschaft zur Ü2 Sicherheitsüberprüfung",                                                            # HENSOLDT
    "Das Einverständnis zur Durchführung einer einfachen Sicherheitsüberprüfung nach § 8 SÜG ist Voraussetzung für eine Bewerbung",
    "Willing and eligible to obtain a security clearance",
    "Clearable: must meet all local requirements for high-level security clearance (e.g., no criminal record, fulfillment of national service obligations).",
    "Must be eligible and able to attain relevant national and NATO security clearances",                    # ICEYE
    "Clearance: Ability to obtain appropriate security clearance required for the position.",
    "Eligibility for security clearance; existing clearance is an advantage.",
    "In order to qualify for this exciting career opportunity, you must have a Security Clearance.",
    # found on the 9,925 postings of 2 Oct
    "Active TS/SCI clearance",
    "at least a Secret level government security clearance",
    "Must possess an active Security Clearance - Secret or Top Secret is preferred",
    "Due to the nature of this role, we are looking for someone with EU citizenship.",                       # LiveEO
    "willingness to undergo a security clearance procedure in accordance with the German Security Clearance Act (SÜG)",   # Quantum-Systems
    "Australian citizenship, with eligibility to obtain and maintain an Australian Government Security Clearance (Baseline / NV1 or equivalent)",
    "US Citizen",
    "Secret clearance is required.",                                                                          # Booz Allen Hamilton
]

FLAG = [
    "Successful candidates may need to be eligible for security clearance under German law.",                # SAP, sent 1 Oct
    ("Given the nature of SE3’s work in the defence sector, candidates must be eligible to work on defence-related projects and, "
     "where required, obtain the relevant security clearance."),
    "Due to security clearance requirements, affiliations with countries listed under § 13 para. 1 no. 17 SÜG may affect the application process.",
    "Im Zusammenhang mit möglichen Sicherheitsüberprüfungen können Verbindungen zu Staaten im Sinne des § 13 Abs. 1 Nr. 17 SÜG im Einzelfall berücksichtigt werden.",
    "Candidates with an active Secret or higher clearance are strongly encouraged to apply.",
    "Nice to haves:\n• A Top Secret U.S. security clearance",
    ("Must haves: Eligible for being cleared for a Personal Security Clearance as necessary as well as a citizenship or a "
     "permanent residency in the European Union"),
    "Security Clearance Requirements",
]

OK = [
    ("We are committed to equal employment opportunity regardless of race, color, ancestry, religion, sex, national origin, sexual "
     "orientation, age, citizenship, marital status, disability status, gender identity or Veteran status."),
    "We do not prioritize any specific religion, gender, nationality, or background.",                       # Isar Aerospace, 102 postings
    "Join an interdisciplinary, international team with 60+ different nationalities in a collaborative work environment.",
    "Geschlecht, Nationalität, ethnischer und sozialer Herkunft, Religion, Behinderung, Alter sowie sexueller Orientierung und Identität.",
    "In a time of rising threats, STARK is bolstering the technological edge of NATO Allies and their Partners to deter aggression and defend Europe, today.",
    "Our dual-use unmanned ground systems and sensors assist NATO Armies and civilian first responders.",
    ("As part of the application process, candidates will be asked to provide personal information, including residency status and "
     "nationality, which is required for visa processing."),
    "Creating custom AI applications that will impact millions of citizens",
    "voize welcomes people from all different backgrounds, including age, citizenship, ethnic and racial origins to apply.",
    "Experience in an aerospace or defense environment operating under ITAR/EAR or equivalent national defense export control frameworks is an advantage.",
    "No security clearance is required for this role.",
    "EU citizenship or a valid work permit for Germany is required.",
    "You have a valid work permit to work in Germany",
    "You will clear technical debt and own the customs clearance pipeline.",
    # false alarms found on the 9,925 postings of 2 Oct
    "We provide the resources and opportunities for continuous personal and professional development.",      # "us person" inside "continuous personal"
    "INTERNATIONALITY: Neben unserem HQ in Stuttgart sind auch unsere Offices in Berlin und Amsterdam gewachsen.",
    "You are a true global citizen who thinks and lives internationality.",
    "For non-EU citizens, it's 21 days worldwide.",
    "Write clean, testable, maintainable, and well-documented code and treat security as a first-class citizen",   # Scalable Capital
    "Desire to work in a very fast-paced, high-stakes environment where your work directly impacts citizens",
    "You improve how these businesses operate across their Citizen administration and services ecosystem.",
]


@pytest.mark.parametrize("line", DROP)
def test_nationality_or_firm_clearance_drops(line):
    assert check("We build drones.\n" + line)[0] == "drop"


@pytest.mark.parametrize("line", FLAG)
def test_a_conditional_clearance_line_is_flagged_and_kept(line):
    verdict, lines = check("We build drones.\n" + line)
    assert verdict == "flag" and lines


@pytest.mark.parametrize("line", OK)
def test_a_sentence_that_demands_nothing_is_left_alone(line):
    assert check("We build drones.\n" + line) == ("ok", [])


def test_empty():
    assert check("") == ("ok", []) and check(None) == ("ok", [])


# --- in the pipeline ---------------------------------------------------------------------------------
import json
import os
import subprocess
import sys

from conftest import SCRIPTS

WORK = ("You train and ship PyTorch models for computer vision and you own the evaluation and the data pipeline. "
        "The team is twelve engineers in Munich and the product flies on forty drones. ")
NATO = "Nationality of a NATO member nation or close ally is required."
MAY = "Successful candidates may need to be eligible for security clearance under German law."


def test_the_filter_drops_a_nationality_row_unread_and_marks_a_conditional_one(tmp_path):
    sc = tmp_path / "sc"
    sc.mkdir()
    for src in ("ba", "getro", "talent", "arbeitnow", "linkedin", "xing", "stepstone"):
        (sc / (src + ".json")).write_text("[]")
    def row(i, tail, **kw):
        return dict(company=["", "Zzalpha Robotics", "Zzbeta Vision", "Zzgamma Labs"][i], title="Machine Learning Engineer", location="Berlin, Germany",
                    url="https://zz.example/%d" % i, date="2099-01-01", desc=WORK * 5 + tail, source="greenhouse", **kw)
    (sc / "ats.json").write_text(json.dumps([row(1, NATO), row(2, MAY), row(3, "English is the working language.")]))
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "filter_run.py"), str(sc)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-2000:]
    got = {c["company"]: c for c in json.load(open(sc / "candidates.json"))}
    assert set(got) == {"Zzbeta Vision", "Zzgamma Labs"}
    assert got["Zzbeta Vision"]["clearance_flag"] == [MAY] and "clearance_flag" not in got["Zzgamma Labs"]
    off = json.load(open(sc / "clearance_off.json"))
    assert off[0]["job"].startswith("Zzalpha Robotics") and off[0]["line"] == NATO
    assert "Nationality or clearance required, dropped unread: 1" in p.stderr


def test_a_fetched_row_gets_the_same_split(tmp_path):
    import fetch_desc as FD
    rows = [dict(company="A", title="CV Engineer", source="getro:x", url="a"), dict(company="B", title="CV Engineer", source="getro:x", url="b")]
    (tmp_path / "candidates.json").write_text(json.dumps(rows))
    s = FD.run(str(tmp_path), {"*": lambda j: dict(j, desc=WORK * 5 + (NATO if j["company"] == "A" else MAY), desc_src="page")})
    got = json.load(open(tmp_path / "candidates.json"))
    assert s["clearance"] == 1 and [c["company"] for c in got] == ["B"] and got[0]["clearance_flag"] == [MAY]
    assert json.load(open(tmp_path / "clearance_off_fetched.json"))[0]["line"] == NATO


def test_a_nationality_line_cannot_be_waved_through_and_a_conditional_one_lands_in_the_gaps(tmp_path):
    import datetime
    import read_next as R
    import verdict as V
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = [dict(id="a", company="A", title="CV Engineer", url="https://a.example", source="web", desc=WORK * 5 + NATO),
            dict(id="b", company="B", title="CV Engineer", url="https://b.example", source="web", desc=WORK * 5 + MAY)]
    (tmp_path / "candidates.json").write_text(json.dumps(rows))
    (tmp_path / "run_slot.json").write_text(json.dumps(dict(date="2026-10-02", slot="evening", started=now.isoformat())))
    sc = str(tmp_path)
    R.main(["x", sc])
    printed = R.log(sc)["printed"]
    base = dict(fit=8, gate="", band="A", lang_line="no language line in the posting", reason="Detection and edge deployment, his SPHF work.", hard_req="none")
    clean, why = V.check(dict(base, id="a"), {r["id"]: r for r in rows}, printed)
    assert clean is None and "Reject it with gate clearance" in why
    clean, why = V.check(dict(base, id="a", gate="clearance", reason="NATO nationality is required, a non-EU national cannot meet it."), {r["id"]: r for r in rows}, printed)
    assert clean["verdict"] == "reject"
    (tmp_path / "verdicts.json").write_text(json.dumps({"b": V.check(dict(base, id="b"), {r["id"]: r for r in rows}, printed)[0]}))
    job = V.lists(sc)["jobs"][0]
    assert job["company"] == "B" and MAY[:60] in job["gaps"] and job["gaps"].startswith("Clearance or nationality line")
