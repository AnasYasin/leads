"""collect_ats.parse keeps the whole text of a posting, cleaned (docs/PROBLEMS.md 1.3 and the field audit
of 2 Oct 2026). Each case is the shape of a real board response, cut down."""
import json

import collect_ats as C
from textclean import leftovers

BULLET = "• "


def one(kind, raw, slug="acme"):
    rows = C.parse(kind, slug, "Acme", raw if isinstance(raw, str) else json.dumps(raw))
    assert len(rows) == 1 and leftovers(rows[0]["desc"]) == {}
    return rows[0]


def test_greenhouse_escaped_html_comes_out_clean():
    # All 3,029 Greenhouse rows kept their markup: the old strip removed tags before decoding them.
    r = one("greenhouse", {"jobs": [{"title": "ML Engineer", "absolute_url": "u", "location": {"name": "Berlin"},
                                     "content": "&lt;p&gt;&lt;strong&gt;About&lt;/strong&gt;&lt;/p&gt;&lt;ul&gt;&lt;li&gt;PyTorch&lt;/li&gt;"
                                                "&lt;li&gt;Fluent German&lt;/li&gt;&lt;/ul&gt;"}]})
    assert r["desc"] == "About\n" + BULLET + "PyTorch\n" + BULLET + "Fluent German"


def test_lever_keeps_the_lists_and_the_closing_section():
    # `descriptionPlain` is the opening only. On the one `lever` board the lists and the closing part
    # held 8,400 of 9,100 characters per job, the requirements among them.
    r = one("lever", [{"text": "ML Engineer", "hostedUrl": "u", "categories": {"location": "Berlin"}, "createdAt": 1,
                       "descriptionPlain": "Opening.", "description": "<div>Opening.</div>",
                       "lists": [{"text": "What you bring", "content": "<li>Python</li><li>German at C1</li>"}],
                       "additional": "<div>We sponsor visas.</div>", "salaryDescription": "<div>EUR 70-90k</div>"}])
    assert r["desc"].split("\n") == ["Opening.", "", "What you bring", BULLET + "Python", BULLET + "German at C1",
                                     "We sponsor visas.", "EUR 70-90k"]


def test_pinpoint_keeps_responsibilities_and_skills():
    # There is no `requirements` field on Pinpoint. 3,200 of 5,100 characters were lost.
    r = one("pinpoint", {"data": [{"title": "ML Engineer", "url": "u", "location": {"city": "Berlin"},
                                   "description": "<p>Intro.</p>", "key_responsibilities": "<ul><li>Train models</li></ul>",
                                   "skills_knowledge_expertise": "<ul><li>Sehr gute Deutschkenntnisse</li></ul>",
                                   "benefits": "<p>30 days</p>"}]}, slug="acme.example")
    d = r["desc"]
    assert d.index("Intro.") < d.index("Key responsibilities") < d.index(BULLET + "Train models") \
        < d.index(BULLET + "Sehr gute Deutschkenntnisse") < d.index("30 days")


PERSONIO = """<workzag-jobs><position>
    <id>2571892</id><subcompany>Acme GmbH</subcompany><office>Berlin</office><department>R&amp;D</department>
    <name>ML Engineer (m/f/x)</name>
    <jobDescriptions>%s</jobDescriptions>
    <employmentType>permanent</employmentType><seniority>experienced</seniority><keywords>AI,Sales</keywords>
    <createdAt>2026-03-20T15:48:39+00:00</createdAt>
    <salaryInformation><min>55000.00</min><max>80000.00</max><currencySymbol>€</currencySymbol>
        <currencyCode>EUR</currencyCode><type>yearly</type></salaryInformation>
</position></workzag-jobs>"""


def test_personio_text_is_the_sections_and_nothing_else():
    secs = ("<jobDescription><name>Your mission</name><value><![CDATA[<p>Build <strong>models</strong>.</p>]]></value></jobDescription>"
            "<jobDescription><name>Your profile</name><value>\n<![CDATA[<ul><li>Python</li></ul>]]>\n</value></jobDescription>")
    r = one("personio", PERSONIO % secs)
    assert r["desc"] == "Your mission\nBuild models.\n\nYour profile\n" + BULLET + "Python"
    assert r["salary"] == "EUR 55000-80000" and r["title"] == "ML Engineer (m/f/x)" and r["date"].startswith("2026-03-20")


def test_personio_position_without_text_has_an_empty_description():
    # 278 of 623 Personio rows on 2 Oct 2026. The old strip filled `desc` with the id, the department
    # and the keywords, so the row looked read and its text was never fetched.
    r = C.parse("personio", "acme", "Acme", PERSONIO % "")[0]
    assert r["desc"] == "" and r["salary"] == "EUR 55000-80000"


def test_ashby_recruitee_workable_teamtailor():
    html = "<h2>Role</h2><p>Train models.</p><ul><li>German is a plus</li></ul>"
    want = "Role\nTrain models.\n" + BULLET + "German is a plus"
    assert one("ashby", {"jobs": [{"title": "T", "jobUrl": "u", "location": "Berlin", "descriptionHtml": html}]})["desc"] == want
    assert one("recruitee", {"offers": [{"title": "T", "careers_url": "u", "description": html,
                                         "requirements": "<p>Python</p>"}]})["desc"] == want + "\nPython"
    assert one("workable", {"jobs": [{"title": "T", "url": "u", "description": html}]})["desc"] == want
    assert one("teamtailor", {"items": [{"title": "T", "url": "u", "content_html": html}]})["desc"] == want


def test_keep_raw_is_off_by_default_and_nothing_is_cut():
    big = "<p>" + "</p><p>".join("Line %d of the posting." % i for i in range(3000)) + "</p><p>Last line.</p>"
    r = one("ashby", {"jobs": [{"title": "T", "jobUrl": "u", "location": "Berlin", "descriptionHtml": big}]})
    assert "desc_raw" not in r and len(r["desc"]) > 60000 and r["desc"].endswith("Last line.")


def test_importing_the_collector_fetches_nothing():
    assert callable(C.main) and len(C.BOARDS) > 100
