# Deploying the radar

Do this after `SETUP.md` has been completed and `python3 scripts/setup_check.py` prints `READY`.

## 1. The repository

Push the set-up copy to a **private** GitHub repository. It will hold your applications log, every
posting sent to you and your profile, so it is never public.

Install the Claude GitHub app on that repository: github.com/apps/claude, grant it the one
repository. Authorising the app is not enough; it has to be installed, or the routine cannot clone
or push.

## 2. Delivery

Every run pushes its results into this repository, and that is the store: `shortlists/<date>-<slot>.md`
and `.json`, one pack per sent job under `jobs/` with `jobs/index.json`, and `companies/*.json`.
`reports/LATEST.md` always holds the newest two runs. Nothing is sent anywhere by default. On a laptop,
`python3 scripts/store.py` after a pull builds `store/jobs.db`, a SQLite file with every sent job, its full
description, its applied status from `state/applications.md` and the days since it was posted; the
`open_jobs` view is the list to apply from. `--check` re-checks each open link and records live or gone.

Email over Gmail is optional. It runs only when two repository secrets exist, under Settings,
Secrets and variables, Actions: `GMAIL_ADDRESS`, the Gmail address that sends and receives, and
`GMAIL_APP_PASSWORD`, an app password for that account. Nothing else sends mail. The cloud run never
has mail access.

## 3. The routines

Two scheduled cloud agents on claude.ai/code, Routines. Both use one cloud environment with this
repository as the source and the tools Bash, Read, Write, Edit, Glob, Grep, WebSearch, WebFetch.

**Morning and evening.** Cron `0 8,17 * * *` (UTC; 09:00 and 18:00 Berlin in winter, move it by an
hour when the clocks change). **Noon.** Cron `30 12 * * 1,4`, Monday and Thursday; it reads what the
other runs left unread. Pick hours for your own time zone; `scripts/slots.py` names the slot from the
UTC hour (morning before 10:00 UTC, noon 10:00 to 15:00, evening after).

The routine prompt is short. Both routines use the same text:

```
You are the job radar for <name>. Work in the repository <owner>/<repo>.

1. Run `python3 scripts/slots.py`. It prints the slot of this run: morning, noon or evening.
2. Read instructions/PROMPT.md from top to bottom and follow it exactly for that slot. It is the only
   source of instructions. If this prompt and instructions/PROMPT.md disagree, instructions/PROMPT.md wins.
   The repo layout is in README.md: state/ (files carried between runs), reports/, instructions/, docs/.
3. Read jobs only through `python3 scripts/read_next.py $SC` and hand in verdicts only through
   `python3 scripts/verdict.py $SC -`. Never write a helper of your own that prints or shortens job texts.
4. Collection writes `candidates.json` into the scratch directory `$SC`, not into the repository.
5. Render once with `python3 scripts/write_pack.py $SC/shortlist.json`, then push with
   `python3 scripts/gitsync.py push -A -m "Job radar, {date} {slot}, {n} new"`.

Never apply to anything. Never send mail or create a draft. This routine has no Gmail connector:
skip section 8 of instructions/PROMPT.md (the mailbox scan) in every run, including the evening run.
```

Behaviour is changed by editing files in the repository and pushing, never by editing the routine.

## 4. The first run

Run the morning routine once by hand from its page. Then check three things.

1. A commit `Job radar, <date> morning, <n> new` arrived in the repository, with
   `shortlists/<date>-morning.md`.
2. The Deliver shortlist Action ran green and `reports/LATEST.md` holds the run.
3. The part of the shortlist file below `## Run details` names every source with a row count, and
   the `Source health` block has no `SOURCE ZERO` line. A source at zero on the first run is usually a
   blocked network egress; the environment's network setting must allow the job sites.

The first weeks send more than later ones, because the memory files in `state/` start empty. Every
job read is remembered for 14 days and every job sent for 90, so the volume settles.

## 5. Optional: the archive of each run's working files

`scripts/archive_run.py` uploads each run's working files as a GitHub Release when
`RADAR_GITHUB_TOKEN` is set in the cloud environment. Routine sessions on claude.ai are not allowed
to create releases at the time of writing, so this step prints `archive: failed` there and does
nothing else. Leave the variable unset unless that changes.

## 6. The laptop side

The cloud finds and ranks. Applying is done by hand, and the applications log that the cloud reads
to skip applied roles is `state/applications.md`, one row per job in the table format at the top
of the file. Keep it current, by hand or with a script of your own that commits and pushes it, and
the next run stops sending those roles.
