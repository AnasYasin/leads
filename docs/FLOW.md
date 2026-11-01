# How a radar run works, end to end

Updated 29 Sep 2026. This file describes the whole flow in the order it happens. `instructions/PROMPT.md` holds the
instructions the cloud agent follows, and `instructions/PROFILE.md` holds the scoring rules. When this file and
`instructions/PROMPT.md` disagree, `instructions/PROMPT.md` wins, because it is what the agent reads.

## Schedule

All times are Berlin time. They hold in summer time (CEST, until 25 Oct 2026). The routines and
workflows are scheduled in UTC underneath, so after the clocks go back on 25 Oct every run lands an
hour earlier on the Berlin clock (09:00, 12:30 and 18:00 for the radar) unless the crons are moved.

| What | When (Berlin time) | Where | Output |
|---|---|---|---|
| Job radar, morning | 10:00 daily, email around 10:30 to 10:50 | Claude routine in the cloud | `shortlists/<date>-morning.md` and the email |
| Job radar, noon (backlog) | 13:30 daily | Claude routine `job-radar noon` in the cloud | `shortlists/<date>-noon.md`: reads the jobs the morning and evening runs left unread |
| Job radar, evening | 19:00 daily, email around 19:30 to 19:50 | Claude routine in the cloud | `shortlists/<date>-evening.md`, the email, the mailbox scan |
| Funded-startup sweep | inside a run, when 7+ days have passed since the last one | same run | new boards in `instructions/COMPANIES.md` |
| Follow-up list | 09:00 Monday | Claude routine | `followup/<week>.md` and its email |
| Weekly report | Saturday evening, 19:40 | Claude routine and `weekly.yml` | `weekly/<week>.md` |
| Monthly summary | last day of the month, 19:50 | `monthly.yml` | `monthly/<month>.md` |
| Laptop pull | every 30 minutes and after wake-up | `radar-autopull.timer` | the laptop copy of this repo |
| Tests | every push that touches `scripts/`, `tests/` or `config/` | `tests.yml` on GitHub | a green or red check |

The code decides the slot from the UTC hour in `scripts/slots.py`: morning before 10:00 UTC, noon
from 10:00 to 15:00 UTC, evening after. That rule is internal; every time shown to the candidate is Berlin time.

The noon run collects nothing. The morning and evening runs end by writing every candidate they did
not read into `state/leftover.json`, and the noon run reads that list from the top (`scripts/leftover.py`).
Every job any run reads goes into `state/backlog_done.json` for 14 days and never enters the list again, so
the noon run never reads a job twice. New postings wait for the evening run.

## Configuration

Every search term, title filter, location list, recruiter and applied-company list and read-order
weight lives in `config/radar.yaml`, read by `scripts/cfg.py`. Nothing about the candidate or the kind
of job is written into the scripts, so pointing the radar at another person or another role means
editing that file and `instructions/PROFILE.md`. `python3 scripts/cfg.py` checks every pattern compiles. An empty
list matches nothing, and a bare `no` or `on` in a pattern list is refused, because YAML reads it as a
boolean.

## One run, step by step

### 1. Collect

`python3 scripts/collect_all.py $SC` runs every collector in parallel. Each writes one JSON file into
the scratch folder `$SC` and a log beside it.

| Source | Collector | What comes back | Window |
|---|---|---|---|
| Bundesagentur für Arbeit | `collect_ba.py` | cards; the detail is fetched later | recent |
| Company boards | `collect_ats.py` | full descriptions and real dates | whatever is open |
| LinkedIn | `collect_linkedin.py` | cards only | last 24 hours |
| XING | `collect_xing.py` | descriptions, dates, employer apply links | last 14 days |
| StepStone | `collect_stepstone.py` | descriptions (works from the cloud only) | last 3 days |
| de.talent.com | `collect_talent.py` | cards | no date |
| arbeitnow | `collect_arbeitnow.py` | descriptions | ingest date only |
| VC portfolio boards (Getro) | `collect_getro.py` | cards | morning run only |

`collect_ats.py` polls every board listed in `instructions/COMPANIES.md` as a `kind | slug | name | note` line,
plus the entries in its own `BOARDS` list. Adding a board to `instructions/COMPANIES.md` is enough to get it polled.
That has been true since 29 Sep 2026. Before then 51 documented boards were never polled.

### 2. Filter

`collect_all.py` then runs `scripts/filter_run.py`. It keeps rows with a relevant title and a usable
location, and removes the ones below.

| Removed | How | Where it goes |
|---|---|---|
| PhD and student roles | title rules | `phd_off.json` |
| Already sent | `is_repeat` against `state/seen.json`: every stored link, the Bundesagentur reference, "@Employer" in the title, and the description when the company is blank or wrong. A second opening (the sent job still live in the pool under its own link, and a real word differs in the title) is kept and tagged `similar_to_sent` | `repeats.json` |
| Same role already applied to | `state/applications.md` | counted only |
| Rejected earlier on a German or clearance line, last 14 days | `state/rejected.json` via `scripts/rejected.py` | `rejected_before.json` |
| A strong German requirement in the description | `lang_band.hard_drop` | `german_off.json` |

Descriptions are then trimmed by `scripts/trim_desc.py`. Short perk sentences (vacation, JobRad, gym,
canteen, discounts, pension) and equal-opportunity boilerplate go. Responsibilities, the company
description, pay, language, location and visa lines are never removed, and no piece longer than 300
characters is touched. The reader scripts print trimmed text too. On 442 descriptions it cut 2.4%
and changed no salary or German decision.

What is left is ranked by `scripts/prescore.py` and written to `candidates.json`, best first. The
score uses the title, his tools in the description, seniority and infrastructure penalties, freshness,
and a LinkedIn bonus because its window is 24 hours. A row with no description gets the median
description score of the run's described rows. It never removes a row.

### 3. Sweep and health

Still inside `collect_all.py`.

- `scripts/sweep_due.py` prints `DUE` or `NOT DUE`. When due, it writes `sweep_leads.txt` from the
  deutsche-startups.de funding feed, and the agent runs the sweep in this run.
- `scripts/health.py` records the rows per source and every board's result in `state/health.json`, keeps
  the ranked candidates in `state/health_candidates.json`, and prints the flags (`SOURCE LOW`, `SOURCE ZERO`,
  `BOARD DEAD`, `BOARD EMPTY`, `BOARD NEW`, `FIRST RUN`).
- On the evening run, `scripts/prune_packs.py` deletes the pack of a job he never applied to once
  the job is really gone. All of these must hold. The pack was sent 20 or more days ago. There is no
  applied row for it (matched loosely, because titles get edited) and no `applied` stamp in the pack.
  Its apply and fallback links both check GONE. The job is not in this run's collected pool, and its
  board did not fail in this run. It was GONE on an earlier check at least a day before. The pool condition exists because on 29 Sep 2
  of 9 GONE packs were still being collected under a new link. Deletions are logged in `state/prune.json`.

### 4. Read, research, score

The agent reads `candidates.json` from the top. Each posting is read in full (`read_jobs.py`,
`read_linkedin.py`, `read_talent.py` fetch the text for rows that arrive as cards). It finds the
employer's own apply link, checks the German line, researches the company (the `companies/` cache
first), and scores fit 0 to 10 against `instructions/PROFILE.md`. A job needs fit 6 to be sent. Priority is fit
plus freshness and source bonuses, and it only decides the order. Each job gets a `size_class` for the
salary ask.

Before reading, the agent drops plainly unrelated titles (`scripts/triage.py`), then
`scripts/fetch_desc.py` fetches the full text for every row that has none, from any source
(`scripts/jobpage.py` reads a posting from its link), drops those with a strong German requirement into
`german_off_fetched.json`, and sorts the list again. No description is cut at any length, and every
description goes through one cleaner (`scripts/textclean.py`). Rows with no readable text are listed in
`no_text.json`, closed postings in `gone.json`.

Reading goes through one reader. `scripts/read_next.py` prints a few jobs whole, the agent hands in a
verdict for each with `scripts/verdict.py`, and only then gets the next batch. What was read is taken
from the reader's log, and a job the reader did not print is not sent. Every verdict is stored in
`state/decisions.json`, and a job read in the last 14 days is not read again unless its text changed.

A run reads until 80 minutes after collection started (`slots.py --elapsed`) and aims to finish in about 90. That puts the morning email near 11:45, the noon one near 15:00 and the evening one near 20:45. Unread rows are not lost. They go into the noon backlog, and they
come back in later runs until they leave their source's window.

### 5. Render

The agent writes `$SC/shortlist.json` and runs `python3 scripts/write_pack.py $SC/shortlist.json`.

| Output | What it is |
|---|---|
| `shortlists/<date>-<slot>.md` | the email: jobs by German band, coverage table, reading counts, source health, rejected list |
| `shortlists/<date>-<slot>.json` | the same run as data |
| `jobs/<id>.md` and `jobs/index.json` | one pack per sent job, read by `pick.py` on the laptop |
| `state/seen.json` | every sent job, pruned to 90 days |
| `state/rejected.json` | the run's German and clearance kills, merged in |
| `companies/<slug>.json` | the company cache, written by the cloud and the laptop |
| `reports/HEALTH.md` | the per-run health table, rebuilt |

`write_pack.py` also checks each apply link is live, takes the posting date from the employer's board,
reads a salary out of the description when the agent left it empty, and adds an `Ask for:` line from
the candidate's table in `scripts/salary.py` when the posting names no figure.

### 6. Push and deliver

`python3 scripts/gitsync.py push -A -m "Job radar, <date> <slot>, <n> new"` commits everything and
pushes. A push that touches `shortlists/` starts `deliver.yml`, which rebuilds `reports/LATEST.md` and, when the
Gmail secrets are set, emails the newest shortlist through `send_mail.py`.

### 7. Evening only: the mailbox

The evening run reads the mailbox for application confirmations, rejections, interviews and
assessments, and records them in `pipeline/events.json`, rendered as `reports/PIPELINE.md`. Rows it finds for
applications missing from `state/applications.md` are added there and merged to the laptop by `pick.py`.

## State files, and who writes them

| File | Written by | Read by | Purpose |
|---|---|---|---|
| `config/radar.yaml` | people | `cfg.py`, the collectors, `filter_run.py`, `prescore.py` | search terms, filters, weights |
| `state/seen.json` | `write_pack.py` | `filter_run.py`, `write_pack.py`, `final_check.py` | never send a job twice; records the slot since 29 Sep 2026 |
| `state/leftover.json` | `write_pack.py` via `leftover.py` | `collect_all.py` at noon | the backlog the noon run reads |
| `state/backlog_done.json` | `write_pack.py` via `leftover.py` | `leftover.py` | every job a run read, 14 days, kept out of the backlog |
| `state/rejected.json` | `write_pack.py` | `filter_run.py` | skip German and clearance kills for 14 days |
| `state/sweep.json` | `sweep_due.py --done` | `sweep_due.py` | when the funded-startup sweep is due |
| `state/health.json` | `health.py` | `health.py`, `write_pack.py` | source and board history, 30 runs |
| `state/health_candidates.json` | `health.py` | people | the last run's ranked candidates |
| `state/prune.json` | `prune_packs.py` | `prune_packs.py`, people | first GONE check per pack, and every deletion |
| `reports/HEALTH.md` | `health.py --render` | people | the health table |
| `instructions/COMPANIES.md` | the agent, people | `collect_ats.py` | boards to poll |
| `state/applications.md` | `pick.py` on the laptop, the evening run | `filter_run.py`, the agent | what he researched and applied to |
| `pipeline/events.json` | the evening run, `pick.py pipeline add` | `pipeline.py` | the application ledger |
| `companies/*.json` | `write_pack.py`, `company_cache.py` | both sides | what is known about each employer |

## The laptop side

`~/job_hunt/scripts/pick.py` is the bridge. Every call pulls this repo first and pushes
`state/applications.md` back when it changed.

The laptop copy also stays current on its own. A user systemd timer, `radar-autopull.timer`, runs
`~/job_hunt/scripts/radar_autopull.sh` every 30 minutes and after the laptop wakes. It calls
`gitsync.py pull`, skips a repo that is mid-rebase or mid-merge, and logs to
`~/.cache/radar-autopull.log`. Check it with `systemctl --user list-timers radar-autopull.timer`.

- `pick.py` lists the recent packs, and `pick.py <n>` prints one with a live check.
- `pick.py applied <n>` records an application with the date and the CV and cover letter used.
- Batch mode ("make a batch") is described in `~/job_hunt/CLAUDE.md`. It takes the newest run first,
  then the backlog, builds a CV per job and reports each job in the block format.

## Checking health

Open `reports/HEALTH.md`. One row per run shows what each source returned, how many candidates were left, how
many were read and left unread, the run time and the jobs sent. Below it are the open flags and the
boards failing now, with how many runs in a row. A source whose row count drops, or a board failing
three runs running, is the thing to look at. The email carries the same flags under `Source health`.

## Testing

`make ci` runs `pytest -q tests` in the `jobsearch` conda environment, the same command as the GitHub
workflow. The tests cover the repeat check, the German rules, the rejection memory, salary extraction
and the ask table, the pre-score, the health flags and table, the sweep schedule and feed, the board
list read from `instructions/COMPANIES.md`, a full `write_pack.py` render in a temporary copy of the repo with the
network stubbed, the pack cleanup with every one of its guards, the backlog, the description fetch,
and the configuration. `tests/data/config_golden.json` holds every rule as it was written into the
scripts before the move to `config/radar.yaml`, so the tests prove the move changed nothing. Run
`make ci` before every push to `scripts/` or `config/`.

To test the collectors without touching the repo, run them into a scratch folder with
`RADAR_HEALTH_DRY=1 python3 scripts/collect_all.py /tmp/somewhere`. StepStone and the Greenhouse boards
do not answer from the laptop, so their results only mean something from the cloud.
