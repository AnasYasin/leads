# Candidate profile — <fill: full name>

This file is the scoring brain for the job radar agent. Score every job against it. Do not flatter, do not stretch. A wrong 9 wastes his morning.

## Who he is

<fill: three to five lines. Role and field in one line. City and country. Nationality and work permit status
(this decides the citizenship and clearance gate). Degrees with years. Total years of experience and how many
in the country of the search.>

## Experience

<fill: one paragraph per job, newest first. Employer, city, role, dates. What was built, with the real tools
and the real results. The agent scores against these paragraphs, so a tool that is not named here does not
exist for scoring. Take every fact from the CV and ask for what the CV does not say.>

## Flagship projects

<fill: the two to four projects the candidate would talk about in an interview. One paragraph each, with scale,
tools and results. Leave the section out if there is none.>

## Tools he has really used

<fill: a plain list of languages, frameworks, libraries, platforms and clouds the candidate has used for real
work. Nothing aspirational. The agent treats anything not listed as a gap.>

## Target roles

<fill: the roles wanted, most wanted first. Say which role types are off, and why, so the agent can log them
under Rejected with the right gate. Say whether PhD positions, internships and working-student roles are in or
out. Name the kinds of work that are not wanted at all, such as business intelligence or sales engineering.>

## Location rules

<fill: where the candidate will work. Cities, regions or the whole country. Whether fully remote counts, and
from where. Whether hybrid outside the country is acceptable. The code's location filter is the city list in
config/radar.yaml under filters.location_ok; this section tells the agent how to judge the rest.>

## Language rule

<fill: the candidate's level in the local language, as a CEFR letter, e.g. B1>. The code's bands below are written for B1 (scripts/lang_band.py drops B2 and above unread); a candidate at B2 or better needs that script changed before the first run, and the setup session must say so. Every job gets a language band, and the email is split by it (see instructions/PROMPT.md section 6).

- **Band A, little or no German.** German is not mentioned, is a plus, nice to have, "von Vorteil", "wünschenswert", or the posting says English is the working language.
- **Band B, German at B1.** The posting asks for German at B1, "gute Deutschkenntnisse", "solide Deutschkenntnisse", "sichere Deutschkenntnisse", "kommunizierst sicher auf Deutsch", "Deutsch in Wort und Schrift", "Deutschkenntnisse erforderlich", or it is a German-language advert that names no level. These are wanted. He works in German at B1 and is improving.
- **Drop.** B2, C1, C2, fließend, verhandlungssicher, muttersprachlich, "sehr gute Deutschkenntnisse", "fluent German", "business-level German", or a stated German-only working environment.

Decided by the candidate on 2 Oct 2026. B2 is a drop, the same as in his batch screen ("sehr gute Deutschkenntnisse (B2)", "mindestens B2"). "Sichere Deutschkenntnisse" and "kommunizierst sicher auf Deutsch" stay Band B. A German-language advert that names no level stays Band B. "Sehr gute Deutschkenntnisse runden dein Profil ab" is a drop, the phrase "runden ab" does not soften it.

**Certain lines are dropped by the code, unclear lines are yours to decide.** `scripts/lang_band.py` drops a job unread only when one sentence gives German a Drop-band level and nothing in that sentence softens it or offers English in its place. When the line is unclear, the row stays and carries the sentences in `german_decide`. Unclear means the sentence also softens the level ("C1 von Vorteil, B2 ausreichend"), offers other languages ("C2 in German, Italian or French"), uses a strong word that is not a level ("kommunikationsstark in Deutsch", "strong German skills"), names German as the working language, or the posting demands German in one place and calls it a plus in another. Read the posting around each such line and decide. Either reject the job with gate `german`, or keep it and quote the sentence in `lang_line`. `final_check.py` prints `GERMAN?` and stops the send while the sentence is not quoted.

Quote the exact language sentence from the posting in the email for every job, so he can judge it himself. If the posting says nothing about language, say "no language line in the posting" and put it in Band A.

## How to score fit, 0 to 10

Start from the core of the job. What would he do most days, and has he done that thing before.

- 9 or 10. The main work matches his real experience directly, and every essential requirement appears somewhere in this profile. Example, a computer vision engineer role wanting PyTorch, detection or segmentation, and deployment.
- 8. Strong match with one gap he could close quickly, or a seniority stretch of about a year.
- 6 or 7. Related but the day to day differs, or two or more essential requirements are missing.
- Below 6. Do not send it.

What happens at each score (the candidate, 2 Oct 2026). Fit 7 or higher is sent in full, and every such job is sent: there is no cap. Fit 6 is listed as one line. Fit 5 or lower with no gate is listed as borderline.

Automatic disqualifiers regardless of everything else: German in the Drop band above, 8 or more years of experience required, EU or NATO citizenship requirement, a security clearance the candidate cannot get (see nationality under Who he is), an unpaid or equity-only role.

Seniority calibration. <fill: the candidate's years of experience, which levels fit, the years figure above which a role is out, and the sweet spot. Example: 6 years, mid level and senior, 8+ years out, 3 to 6 years the sweet spot.> A role with line management, or with a staff, principal, lead or head title, is out.

Paid research internships count when the research content is a strong match (contrastive or self-supervised learning, representation learning, geospatial AI, medical imaging, audio). Score them on the work. Drop unpaid ones, ones needing current student enrolment, and ones with no real research content. Working student roles are out. PhD positions are off, see Target roles.

Recruiter and agency postings count (added 8 Sep 2026). Recruiters are a strong channel in Germany. Keep a recruiter posting when the technical requirements are concrete and the location is real, even if the end client is not named. Score it on the requirements. Give the consultant's name, email and phone when the posting has them, and say plainly that the employer is not named. Drop the evergreen kind, meaning a generic title with no real requirements list, and drop training providers. The Bundesagentur API marks these with `istPrivateArbeitsvermittlung` (recruiter) and `istArbeitnehmerUeberlassung` (temp agency). Cap recruiter postings at 3 per run.

## When to reject a job you read (30 Sep 2026)

A rejected job never reaches him, so reject only when it is clearly not for him. Every entry in `rejected` names one of these gates in `gate`, and quotes the posting where the gate is a line in it:

- `german`: a German line in the Drop band above.
- `clearance`: EU or NATO citizenship, or a security clearance the candidate cannot get. A nationality or citizenship requirement always rejects (scripts/clearance.py; a candidate who holds the citizenship a posting asks for needs that script changed). A firm clearance requirement rejects ("eligibility for a security clearance is required", "Bereitschaft zur Ü2 Sicherheitsüberprüfung"). A conditional line does not reject ("may need to be eligible for security clearance", "where required, obtain the relevant security clearance"): the job is scored as usual and the code puts the sentence into its Gaps line. `scripts/clearance.py` makes this split, drops the certain cases unread, and marks the conditional ones `clearance_flag`.
- `years`: 8 or more years of experience required.
- `phd`: a PhD or publications stated as a requirement.
- `non_software`: a hard requirement outside software development that he certainly does not have, such as years of work on robot hardware, a clinical or engineering licence, or lab or physical product work.
- `lead`: a lead, management or head role.
- `field`: not his field at all, per Not wanted above.
- `closed`: the posting is gone.
- `repeat`: already sent, or the same role already applied to.
- `no_text`: no link and no web search gave the posting's text (noon run only, through `scripts/retext.py`). The reason says where you looked.
- `unpaid`: unpaid or equity-only.

**Software skills are never a reason to reject.** A language, framework, library, tool, cloud or platform he has not used is a gap he closes on the job. Do not reject for it, and do not score below 6 because of it.

**A hard requirement he cannot back caps the fit at 6** (the candidate, 2 Oct 2026). This is the one case where a skill moves the score. It applies when the posting demands years of experience in a specific tool or method he has never used and the role is built on it. Examples from 30 Sep: "3+ years of LP/MIP and a commercial solver such as Gurobi" (zooplus), "Copilot Studio" as the prerequisite of a Copilot Studio consultant (Skaylink), "production experience with DCN-V2 and MMoE ranking models" (Delivery Hero). Quote that requirement in `hard_req` of the verdict. The job is then listed as one line with the requirement shown, and he decides whether to apply. It is never rejected for it. A tool that is only listed, with no years and no "must", is an ordinary gap and does not cap anything.

A job that fails no gate but would score 5 is not rejected. Put it in `borderline` with the link and one line on the doubt. The email lists it, and he decides. A rejection without a valid gate is shown as borderline too.

Why: over 128 runs to 29 Sep, 50 jobs one run rejected were sent by a run within the next day, and 19 were at companies he applied to. About 20 of them were judgement calls on years or skills, the rest were facts (German, clearance, closed) that the sending run missed.

## Ranking — freshness can outrank fit

Fit decides whether a job is sent at all. Ranking decides the order, and a fresh job with a smaller pool beats an older tighter match, because the older one may already have two hundred applicants.

Compute a priority score for every job that passed the fit bar.

    priority = fit score + freshness bonus + source bonus

Freshness bonus, from the posting date:
- posted within 24 hours: +2
- 1 to 3 days: +1
- 4 to 14 days: 0
- 15 to 30 days: -1
- older than 30 days, or no date found: -2

Source bonus:
- on the company's own Greenhouse, Lever, Ashby, Personio or careers page, and not yet visible on the big aggregators: +1
- from the Bundesagentur für Arbeit API: +1
- small or unknown employer rather than a household name: +1
- a Berlin startup: +2. This is where he wants to be and where the pools are smallest.
- the company announced a funding round in the last 12 months: +1. They are hiring now and the role is often still only on their own site.
- an unusual requirement mix that few people have, for example contrastive learning plus geospatial, or ML plus agentic LLM systems: +1
- LinkedIn or XING posting less than 24 hours old: +1. He uses these to reach people at the company for a referral before the pool grows, so a fresh LinkedIn job is worth as much as a fresh company-board job.
- recruiter posting: 0

So a job posted yesterday on a company board scoring 7 on fit lands at 10, and a month-old role at a famous company scoring 9 lands at 7. That is the intended behaviour.

**The bonus changes order only, never eligibility.** A job below 7 on fit is never sent in full no matter how fresh it is. Show the fit score and the priority score separately in the email so he can see both.

There is no cap on the email (the candidate, 2 Oct 2026; it was the top 20 by priority since 8 Sep). Every job at fit 7 or higher is sent in full, ordered by priority. Fit 6 jobs follow as one line each. Until 2 Oct every full run sent exactly 20, and 42 jobs at fit 7 or higher sat in "also found", of which only 13 were ever sent.

## Referral companies, send first

<fill: companies where the candidate has a personal contact, and how to handle them, or the single line
"None." The rows of these companies skip the title filters, are sent at a lower fit bar and get a priority
bonus. Mirror the list in config/radar.yaml under profile.referral_companies.>

## Never show the same job twice

The repo holds `state/seen.json`, a list of every job already sent. Read it at the start of every run and write it back at the end. This is the difference between a useful email and noise.

Each entry stores an id, the company, the title, the location, the canonical url, the date first sent, and the fit score.

Build the id as a slug of `company + normalised title + location`, lowercased, punctuation stripped, seniority words like senior, junior, m/w/d, f/m/d, and gender tags removed. Match on this id, not on the url, because the same job appears with a different url on every board.

Rules:
- Skip any job whose id is already in `state/seen.json`.
- The same job found on several boards is one job. Keep the company's own board link as the canonical url and drop the aggregator copies.
- A reposted job with a fresh date but the same id is still a repeat. Skip it.
- Treat a job as new only if both the company and the normalised title are new, or the same company has posted a genuinely different role.
- Drop entries older than 90 days so the file stays small.
- If `state/seen.json` is missing or unreadable, create it empty and say so in the email rather than sending everything again.

Also skip anything whose company appears in the already-applied list below.

## What he already applied to — do not resend

The list lives in `state/applications.md` in this repository. It is a copy of the log his local job_hunt session keeps, synced by `scripts/pick.py` on his laptop. Read it at the start of every run. Do not edit that file from the cloud.

`filter_run.py` drops a candidate only when the log holds the same role at the same company. A different role at a company he already applied to is kept and tagged `applied_before` with the log row. Send it when it is a real match, and say in `company_note` that he applied there before and for what, so he can decide whether a second application makes sense.

Older names not in the log: <fill: companies applied to before this radar existed, or "none">. Mirror them in config/radar.yaml under profile.applied_companies.

## Companies to never send, whatever the fit

<fill: companies the candidate has ruled out, one line each with the date and the reason, or the single line
"None yet." Drop any job from them before scoring and do not list them in the email.>

