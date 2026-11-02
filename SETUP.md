# Setting this radar up for a new person

Read this whole file first. You are a Claude Code session running in a fresh copy of this repository.
Your job is to fill in `config/person.md`, the one file that describes the person, and generate the
rest from it, so the scheduled runs can find jobs for them. Nothing else. Do not run the radar, do not
push, do not change the scripts.

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

Everything goes into one file, `config/person.md`. It has one heading per answer, with a line under
each saying what belongs there. Write the person's answers under the headings, in the same voice as
the rest of the repository: short sentences, facts only, no praise, no pronoun games (the generated
files say "the candidate"). The CV paragraphs go under Experience. Regular-expression lists
(referral patterns, applied-before names, search terms) are bullet lists, one entry per line.

Then run `python3 scripts/setup_gen.py`. It renders `instructions/PROFILE.md` from
`instructions/PROFILE.template.md` and the person file, writes the `profile` and `search` lists
into `config/radar.yaml`, and puts the salary figures into the `ASK` table of `scripts/salary.py`.
Run it again after every change to the person file; it overwrites those three outputs, so edit the
person file, never the outputs.

Two things it does not touch:

- `filters.location_ok` and the other `filters` and `prescore` lists in `config/radar.yaml`. Leave
  them for a search in Germany. For another country, rewrite `filters.location_ok` with the person,
  one lower-case name per line. If the field is not machine learning or data, rewrite
  `filters.title_good` with them from their target titles and say in the handover that the other
  pattern lists were written for ML jobs.
- `instructions/COMPANIES.md`, the company boards the collector polls. It ships with German AI and ML
  companies. Add a line per board the person names, in the format at the top of the file, and only
  with a slug you have tested against the live board in this session.

## 3. Check, show, confirm

1. Run `python3 scripts/setup_check.py`. It lists every blank still open and every empty search list.
   Fill what it names in `config/person.md`, run `setup_gen.py` again, and repeat until it prints `READY`.
2. Run `make ci`. The tests must pass. If one fails on a value you wrote, show the person the failing
   line and ask; do not edit the test.
3. Print back, in one message, every value you wrote: the profile sections, the search lists per
   site, the salary table, the referral and applied lists. Ask the person to confirm or correct each
   block. Repeat until they confirm all of it.
4. Commit with the message `Set up the radar for <name>`. Do not push; the person pushes.
5. Hand over with the list of code limits you told them about in steps 3 to 5, if any applied, and
   point them to `docs/DEPLOY.md` for the routines, the secrets and the first run.
