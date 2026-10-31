"""scripts/jobpage.py: the full text of a posting from its link (docs/PROBLEMS.md 1.4 and 1.5, 2 Oct 2026).
No test here touches the network: `fetch` is replaced by a table of canned responses."""
import json

import pytest

import jobpage as J

BODY = ("<h2>Your tasks</h2><ul><li>Train and deploy PyTorch models for computer vision on edge devices.</li>"
        "<li>Build the data pipelines and the evaluation that the team relies on every day.</li></ul>"
        "<h2>Your profile</h2><ul><li>Three or more years of Python and deep learning in production.</li>"
        "<li>Fluent English. German is a plus and not a requirement for this position.</li></ul>"
        "<p>We are a team of forty people in Berlin and we build perception software for robots.</p>")


@pytest.fixture
def web(monkeypatch):
    pages = {}

    def fake(url, accept=None, data=None, tries=3, info=None):
        v = pages.get(url)
        if v is None:
            raise J.Gone("HTTP 404")
        if isinstance(v, Exception):
            raise v
        if isinstance(v, tuple):
            v, final = v
            if info is not None:
                info["final"] = final
        elif info is not None:
            info["final"] = url
        return v
    monkeypatch.setattr(J, "fetch", fake)
    J._cache.clear()
    return pages


def test_smartrecruiters_api_gives_every_section(web):
    web["https://api.smartrecruiters.com/v1/companies/Acme/postings/744000152646680"] = json.dumps({"jobAd": {"sections": {
        "jobDescription": {"title": "Job Description", "text": BODY},
        "qualifications": {"title": "Qualifications", "text": "<ul><li>Verhandlungssicheres Deutsch</li></ul>" + "<p>x</p>" * 3},
        "companyDescription": {"title": "Company Description", "text": "<p>Acme builds things.</p>"}}}})
    r = J.read("https://jobs.smartrecruiters.com/Acme/744000152646680-ml-engineer")
    assert r["desc_src"] == "smartrecruiters api"
    lines = r["desc"].split("\n")
    assert lines[0] == "Company Description" and "• Verhandlungssicheres Deutsch" in lines
    assert r["desc"].index("Acme builds") < r["desc"].index("Your tasks") < r["desc"].index("Verhandlungssicheres")


def test_lever_text_includes_the_lists_and_the_closing_part(web):
    web["https://api.lever.co/v0/postings/acme/11111111-2222-3333-4444-555555555555"] = json.dumps({
        "descriptionPlain": "Short opening.", "description": "<div>Short opening about the role at Acme in Berlin.</div>" + BODY,
        "lists": [{"text": "Requirements", "content": "<li>Python</li><li>German C1</li>"}],
        "additional": "<div>We sponsor visas.</div>"})
    r = J.read("https://jobs.lever.co/acme/11111111-2222-3333-4444-555555555555")
    assert r["desc_src"] == "lever api" and "• German C1" in r["desc"] and r["desc"].endswith("We sponsor visas.")


def test_personio_feed_then_page_when_the_feed_has_no_text(web):
    web["https://acme.jobs.personio.de/xml"] = ("<workzag-jobs><position><id>77</id><name>ML Engineer</name>"
                                                "<jobDescriptions></jobDescriptions></position></workzag-jobs>")
    web["https://acme.jobs.personio.de/job/77"] = (
        '<html><head><script type="application/ld+json">%s</script></head><body>x</body></html>'
        % json.dumps({"@type": "JobPosting", "title": "ML Engineer", "description": BODY}))
    r = J.read("https://acme.jobs.personio.de/job/77", "ML Engineer")
    assert r["desc_src"] == "json-ld" and r["desc"].startswith("Your tasks\n• Train and deploy")


def test_json_ld_in_a_graph_and_the_right_job_on_a_list_page(web):
    other = {"@type": "JobPosting", "title": "Sales Manager", "description": "<p>%s</p>" % ("Sell things to customers. " * 20)}
    mine = {"@type": ["JobPosting"], "title": "Computer Vision Engineer", "description": BODY}
    web["https://acme.example/jobs/cv"] = '<script type="application/ld+json">%s</script>' % json.dumps({"@graph": [other, mine]})
    r = J.read("https://acme.example/jobs/cv", "Computer Vision Engineer (m/w/d)")
    assert r["desc_src"] == "json-ld" and "PyTorch" in r["desc"] and "Sell things" not in r["desc"]


def test_main_content_without_the_page_chrome(web):
    web["https://acme.example/careers/ml-engineer"] = (
        "<html><body><nav><a>Home</a><a>Products</a></nav><header>Acme careers</header>"
        "<main><h1>ML Engineer</h1>%s<button>Apply now</button><p>Apply now</p></main>"
        "<footer>Imprint. All rights reserved.</footer></body></html>" % BODY)
    r = J.read("https://acme.example/careers/ml-engineer", "ML Engineer")
    assert r["desc_src"] == "page"
    assert r["desc"].startswith("ML Engineer\n\nYour tasks") and "Products" not in r["desc"] and "Imprint" not in r["desc"]
    assert "Apply now" not in r["desc"]


def test_a_page_about_something_else_is_not_taken(web):
    web["https://acme.example/"] = "<html><body><main>%s</main></body></html>" % ("<p>Acme makes software for hospitals and clinics.</p>" * 20)
    r = J.read("https://acme.example/", "Senior Data Engineer Snowflake")
    assert "desc" not in r and "does not name this job" in r["error"]


def test_a_redirect_to_the_job_list_is_not_the_posting(web):
    # A closed Greenhouse job: the API says 404 and the page lands on the board's list of jobs.
    listing = "<html><body><main>%s</main></body></html>" % "".join("<p>Senior AI Engineer %d</p><p>Berlin</p>" % i for i in range(60))
    web["https://boards.greenhouse.io/acme/jobs/4012345"] = (listing, "https://job-boards.greenhouse.io/acme?error=true")
    r = J.read("https://boards.greenhouse.io/acme/jobs/4012345", "Senior AI Engineer")
    assert r.get("gone") and "desc" not in r


def test_a_plain_404_is_not_proof_that_the_job_is_closed(web):
    # careers.cognizant.com answers a script with 404 and a browser with a bot check (2 Oct 2026).
    r = J.read("https://careers.example/jobs/00068036641/data-engineer", "Data Engineer")
    assert not r.get("gone") and "may be closed" in r["error"]


def test_a_job_list_page_is_refused(web):
    listing = "<html><body><main><p>%s</p>%s</main></body></html>" % (
        "Open roles for an ML Engineer and others at Acme.", "".join("<p>ML Engineer %d</p><p>Berlin</p>" % i for i in range(60)))
    web["https://acme.example/jobs"] = listing
    r = J.read("https://acme.example/jobs", "ML Engineer")
    assert "desc" not in r and "list of jobs" in r["error"]


def test_bot_wall_and_blocked_hosts(web):
    web["https://acme.example/job/1"] = "<html><head><title>Just a moment...</title></head><body>Checking your browser</body></html>"
    assert "bot check" in J.read("https://acme.example/job/1", "ML Engineer")["error"]
    assert "error" in J.read("", "x") and "error" in J.read("not a link")


def test_notion_page_in_reading_order(web):
    pid = "32102b94e5c3817fae7ef0ebb6a906d3"
    dash = "32102b94-e5c3-817f-ae7e-f0ebb6a906d3"

    def blk(kind, text, content=None):
        return {"value": {"type": kind, "properties": {"title": [[text]]}, "content": content or []}}
    web["https://acme.notion.site/api/v3/loadPageChunk"] = json.dumps({"recordMap": {"block": {
        dash: blk("page", "Senior Data Engineer", ["a", "b", "c", "d"]),
        "c": blk("bulleted_list", "Five years of Python and SQL in production systems, on a cloud platform of your choice."),
        "a": blk("sub_header", "About the role"),
        "b": blk("text", "You own the data stack from the warehouse to the models that use it. " * 4),
        "d": blk("page", "Another page")}}, "cursor": {"stack": []}})
    r = J.read("https://acme.notion.site/Senior-Data-Engineer-%s?pvs=25" % pid)
    assert r["desc_src"] == "notion api"
    assert r["desc"].split("\n")[0] == "Senior Data Engineer" and "Another page" not in r["desc"]
    assert r["desc"].index("About the role") < r["desc"].index("You own") < r["desc"].index("• Five years")


def test_one_tries_the_other_links_and_never_raises(web):
    web["https://employer.example/jobs/ml"] = "<main><h1>ML Engineer</h1>%s</main>" % BODY
    row = dict(company="Acme", title="ML Engineer", url="https://www.arbeitsagentur.de/jobsuche/jobdetail/1",
               externe_url="https://employer.example/jobs/ml")
    out = J.one(row)
    assert out["desc_src"] == "page" and out["company"] == "Acme"
    assert "error" in J.one(dict(company="A", title="B", url=""))


def test_compressed_and_binary_responses():
    import gzip
    from email.message import Message
    h = Message(); h["Content-Encoding"] = "gzip"; h["Content-Type"] = "text/html; charset=utf-8"
    assert J._decode(gzip.compress("Grüße".encode()), h) == "Grüße"
    with pytest.raises(J.Unreadable):
        J._decode(bytes(range(128, 256)) * 40, Message())
