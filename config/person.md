# Person

The one file that describes the person this radar searches for. The setup session fills it
(SETUP.md), and `python3 scripts/setup_gen.py` generates `instructions/PROFILE.md`, the `profile`
and `search` lists in `config/radar.yaml` and the salary table in `scripts/salary.py` from it.
Edit this file, never those outputs. One heading per answer; the line in italics under each says
what belongs there and goes away when the answer is written. Lists are bullet lines, one entry each.

## Name

*The full name.*

## Who the candidate is

*Three to five lines. Role and field in one line. City and country. Nationality and work permit
status (this decides the citizenship and clearance gate). Degrees with years. Total years of
experience and how many in the country of the search.*

## Experience

*One paragraph per job from the CV, newest first. Employer, city, role, dates. What was built, with
the real tools and the real results. The agent scores against these paragraphs, so a tool that is
not named here does not exist for scoring.*

## Flagship projects

*The two to four projects the candidate would talk about in an interview, one paragraph each, with
scale, tools and results. Leave empty when there is none; the section is then left out.*

## Tools really used

*A plain list of languages, frameworks, libraries, platforms and clouds used for real work. Nothing
aspirational. The agent treats anything not listed as a gap.*

## Target roles

*The roles wanted, most wanted first. Which role types are off and why (PhD positions, internships,
working-student roles, management, sales engineering, business intelligence...).*

## Location rules

*Where the candidate will work. Cities, regions or the whole country. Whether fully remote counts
and from where. Whether hybrid outside the country is acceptable.*

## Language level

*The CEFR level in the local language of the search, as one token, e.g. B1. The shipped German rule
is written for B1; at B2 or better `scripts/lang_band.py` needs a change before the first run.*

## Seniority

*Years of experience, which levels fit, the years figure above which a role is out, and the sweet
spot. Example: 6 years, mid level and senior, 8+ years out, 3 to 6 years the sweet spot.*

## Salary

*The opening figure per company size, shown in the email as the candidate's own rule, never as the
posting's salary. Leave a figure empty to print no ask line for that class.*

- startup:
- mid:
- large:
- public:

## Referral companies

*Companies where the candidate has a personal contact, and how to handle them, in prose. "None."
when there is none.*

## Referral patterns

*One regular expression per referral company, lower case, as in `\bdhl\b`. Empty when none.*

## Applied before

*Companies applied to before this radar existed, one per line, or nothing.*

## Never send

*Companies the candidate has ruled out, one line each with the date and the reason, or "None yet."*

## Search linkedin roles

*Six to twelve queries: the target titles, their common variants, the local-language forms.*

## Search linkedin places

*Places as LinkedIn names them, e.g. Berlin, Germany.*

## Search bundesagentur queries

## Search bundesagentur places

*Cities, or a single empty-looking entry `''` for nationwide.*

## Search xing queries

## Search xing places

## Search stepstone roles

## Search stepstone cities

## Search talent roles

## Search talent cities
