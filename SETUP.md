# Setting this radar up for a new person

Read this whole file first. You are a Claude Code session running in a fresh copy of this repository.
Your job is to fill in the parts of this repository that describe one person, so the scheduled runs
can find jobs for them. Nothing else. Do not run the radar, do not push, do not change the scripts
except where this file names a line to fill in.

The rule that outranks everything below: **never assume**. Take a fact from the CV when the CV states
it. Ask for everything the CV does not state. Ask again when an answer is vague. The files are
finished when `python3 scripts/setup_check.py` prints `READY` and you have shown the person every
value you wrote and they have confirmed each one.

## 1. What you need from the person

Ask for these in this order. One short message per topic. Say why each one matters in one line.

1. **The CV.** A file in the working tree, or pasted text. Read the whole CV before asking anything
   else, so you do not ask for what it already says.
2. **Target roles.** Which job titles they want, most wanted first. Which kinds of role are out
   (for example PhD positions, internships, working-student roles, management, sales engineering,
   business intelligence). This drives the profile, the title triage and the search words.
3. **Where.** Country of the search. Cities or regions, or the whole country. Whether fully remote
   counts and from where. Whether hybrid outside the country is acceptable. The code ships with a
   German city list and German job boards; if the country is not Germany, say now that the collectors
   for Bundesagentur, XING, StepStone and arbeitnow will return nothing useful and that the title and
   city filters need rewriting. Do not continue past this step without that being understood.
4. **Languages.** Each language they work in, with a CEFR level. The code's German bands are written
   for a B1 candidate (scripts/lang_band.py drops B2 and above unread). If their German is B2 or
   better, tell them that script needs a change before the first run and write that into the notes
   you hand over. Do not change the script yourself.
5. **Nationality and work permit.** Which citizenships they hold, and whether they need sponsorship.
   The code rejects every posting that requires a citizenship or a security clearance
   (scripts/clearance.py). If they hold the citizenship such postings ask for, tell them that script
   needs a change. Do not change it yourself.
6. **Seniority.** Total years of experience, the levels that fit (junior, mid, senior), the years
   figure above which a role is out, and the sweet spot. Take the years from the CV, ask for the rest.
7. **Salary.** Their opening figure for four company sizes: under 50 staff, 50 to 1,000, over 1,000,
   public sector. They may leave any of them empty. These figures are shown to them in the email as
   their own rule, never as the posting's salary.
8. **Referral companies.** Companies where they have a personal contact, or none.
9. **Companies already applied to** before this radar, and **companies never to send**, with the
   reason, or none for either.
10. **Delivery.** The email address the shortlist should go to, and their time zone. These go into
    docs/DEPLOY.md's checklist, not into the files you fill.

Do not invent a value for any of these. Do not fill a section with a plausible guess "to be edited
later". A blank with the person's attention is better than a guess without it.

## 2. Where each answer goes

### instructions/PROFILE.md

Every `<fill: ...>` marker names one blank. Replace the whole marker, brackets included, with prose in
the same voice as the rest of the file: short sentences, facts only, no praise. The markers are:

| Marker | Write |
|---|---|
| title line | the person's full name |
| Who he is | role and field, city and country, nationality and work permit, degrees with years, years of experience |
| Experience | one paragraph per job from the CV, newest first, with the real tools and the real results |
| Flagship projects | the two to four projects they would defend in an interview, or remove the section |
| Tools he has really used | a plain list, only what they have used for real work |
| Target roles | step 2, in their words, with what is off and why |
| Location rules | step 3 |
| Language rule, first sentence | the CEFR level from step 4 |
| How to score, seniority calibration | step 6 |
| Referral companies | step 8, or "None." |
| What he already applied to, older names | step 9, or "none" |
| Companies to never send | step 9, or "None yet." |

Leave every other section as it is. They are the scoring rules the agent follows, and they are not
about the person.

The file uses "he" throughout. Change the pronouns to the person's own in the sections you write,
and leave the general sections alone.

### config/radar.yaml

- `profile.name`: the full name.
- `profile.referral_companies`: one regular expression per referral company, lower case, as in
  `- \bdhl\b`. Empty list when none.
- `profile.applied_companies`: one lower-case pattern per company from step 9. Empty list when none.
- `search.*`: the words each collector searches for. Derive them from step 2. Give each site 6 to 12
  queries: the target titles, their common variants, and the local-language forms. Show the full list
  to the person and ask them to add or strike before you write it. Every list must end up with at
  least one entry, including `places` and `cities`; use the cities from step 3, and `''` for
  nationwide on Bundesagentur.
- `search.linkedin.targets`: extra queries for a referral company with a wider time window, as in
  `- {query: "DHL machine learning", place: Germany, hours: 168}`. Empty list when none.
- `filters.location_ok`: leave the German list when the country is Germany. Otherwise rewrite it
  with the person, one lower-case name per line.
- Everything under `filters` and `prescore` other than that stays as it is unless the person's field
  is not machine learning or data. Then rewrite `filters.title_good` with them, from their target
  titles, and say in the handover that the other pattern lists were written for ML jobs.

### scripts/salary.py

The `ASK` table near the end of the file. Put the four figures from step 7 into the first element of
each tuple, as strings like `"EUR 55-60k"`. Leave a figure empty to print no ask line for that class.
This is the one script you edit.

### instructions/COMPANIES.md

The list of company job boards the collector polls. It ships with German AI and ML companies. Keep
it for a search in Germany. Add a line per board the person names, in the format at the top of the
file, and only with a slug you have tested against the live board in this session.

## 3. Check, show, confirm

1. Run `python3 scripts/setup_check.py`. It lists every blank still open and every empty search list.
   Fill what it names and run it again until it prints `READY`.
2. Run `make ci`. The tests must pass. If one fails on a value you wrote, show the person the failing
   line and ask; do not edit the test.
3. Print back, in one message, every value you wrote: the profile sections, the search lists per
   site, the salary table, the referral and applied lists. Ask the person to confirm or correct each
   block. Repeat until they confirm all of it.
4. Commit with the message `Set up the radar for <name>`. Do not push; the person pushes.
5. Hand over with the list of code limits you told them about in steps 3 to 5, if any applied, and
   point them to `docs/DEPLOY.md` for the routines, the secrets and the first run.
