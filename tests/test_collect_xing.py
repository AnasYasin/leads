"""collect_xing.py reads only the job's own data on a XING page (docs/PROBLEMS.md 1.7, 2 Oct 2026)."""
import json
import os

from conftest import SCRIPTS


def load():
    src = open(os.path.join(SCRIPTS, "collect_xing.py"), encoding="utf-8").read().split("\ndef main():")[0]
    g = {"__name__": "collect_xing_test", "__file__": os.path.join(SCRIPTS, "collect_xing.py")}
    exec(compile(src, "collect_xing", "exec"), g)
    return g


def job(jid, title, company, apply=None, salary=None, text="<p>Text of %s</p>"):
    d = {"__typename": "VisibleJob", "id": "%s.abc123" % jid, "title": title, "activatedAt": "2026-10-01T08:00:00Z",
         "location": {"__typename": "JobLocation", "city": "Wien"},
         "companyInfo": {"__typename": "JobCompanyInfo", "companyNameOverride": company},
         "salary": salary, "description": {"__typename": "JobDescription", "content": text % title},
         "application": {"__typename": "UrlApplication", "applyUrl": apply} if apply else {"__typename": "XingApplication"}}
    return '"VisibleJob:%s.abc123":%s' % (jid, json.dumps(d).replace("/", "\\u002F"))


def page(*jobs):
    return '<html><script>window.STATE = {"ROOT":{"x":"}{"},%s};</script></html>' % ",".join(jobs)


EST = {"__typename": "SalaryEstimate", "currency": "EUR", "minimum": 60000, "maximum": 78500, "median": 70000}


def test_the_apply_link_of_a_similar_job_is_not_taken():
    # Oper, 2 Oct 2026: no company on the card, no apply link of its own, and the first apply link on the
    # page belonged to an Accenture job. A salary estimate of another job was stored as well.
    g = load()
    other = job("111111111", "Applied AI Engineer", "Accenture", apply="https://www.accenture.com/at-de/careers/jobdetails?id=R1", salary=EST)
    own = job("222222222", "AI Solutions Engineer", "Oper", text="<p>%s builds agents</p><ul><li>Python</li></ul>")
    g["fetch"] = lambda u: page(other, own)
    r = g["detail"](dict(xing_id="222222222", url="https://www.xing.com/jobs/x-222222222", company="", title="AI Solutions Engineer"))
    assert r["apply_url"] == "" and r["salary"] == "" and "salary_estimate" not in r
    assert r["company"] == "Oper" and r["location"] == "Wien" and r["date"].startswith("2026-10-01")
    assert r["desc"] == "AI Solutions Engineer builds agents\n• Python"


def test_an_estimate_is_never_the_salary_and_a_stated_band_is():
    g = load()
    g["fetch"] = lambda u: page(job("333333333", "ML Engineer", "Acme", apply="https://acme.example/job/1?utm_source=xing.com", salary=EST))
    r = g["detail"](dict(xing_id="333333333", url="u", company="Acme", title="ML Engineer"))
    assert r["salary"] == "" and r["salary_estimate"].startswith("60000-78500 EUR") and r["apply_url"] == "https://acme.example/job/1"
    stated = {"__typename": "Salary", "currency": "EUR", "minimum": 70000, "maximum": 90000}
    g["fetch"] = lambda u: page(job("444444444", "ML Engineer", "Acme", salary=stated))
    assert g["detail"](dict(xing_id="444444444", url="u", company="Acme", title="ML Engineer"))["salary"] == "70000-90000 EUR"


def test_a_page_without_the_jobs_own_data_guesses_nothing():
    g = load()
    g["fetch"] = lambda u: page(job("111111111", "Other", "Other Co", apply="https://other.example/1", salary=EST))
    r = g["detail"](dict(xing_id="999999999", url="u", company="", title="ML Engineer"))
    assert r["error"] and r["apply_url"] == "" and r["salary"] == "" and not r.get("desc")


def test_a_posting_stored_as_a_template_keeps_every_section():
    # 12 of 279 rows on 2 Oct: the text is not under `content` but in a title and a content field per section.
    g = load()
    tpl = {"__typename": "TemplateData", "sectionTitleColor": None, "genericDescription": "<p>We build inspection robots.</p>",
           "companyDescriptionTitle": None, "companyDescriptionContent": None,
           "responsibilityTitle": "Deine Aufgaben", "responsibilityContent": "<ul><li>Bildverarbeitung</li></ul>",
           "skillsTitle": "Dein Profil", "skillsContent": "<ul><li>Sehr gute Deutschkenntnisse</li></ul>"}
    assert g["html_to_text"](g["description_html"](tpl)) == (
        "We build inspection robots.\n\nDeine Aufgaben\n\u2022 Bildverarbeitung\n\nDein Profil\n\u2022 Sehr gute Deutschkenntnisse")
    assert g["description_html"]({"content": "<p>x</p>"}) == "<p>x</p>" and g["description_html"](None) == ""
    ld = '<script type="application/ld+json">{"@type":"JobPosting","description":"<p>From the JobPosting block</p>"}</script>'
    assert g["ld_description"](ld) == "<p>From the JobPosting block</p>"
