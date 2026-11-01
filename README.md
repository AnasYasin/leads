# job-radar

A scheduled cloud agent that finds jobs for one person and delivers a ranked shortlist twice a day,
with a third run on Monday and Thursday that clears the unread backlog. It finds and ranks. It never
applies.

Built for machine learning and data roles in Germany. The collectors cover the Bundesagentur für
Arbeit, about 200 company job boards (Greenhouse, Lever, Ashby, Personio, Teamtailor, Workable,
Recruitee, SmartRecruiters, join.com), LinkedIn, XING, StepStone, talent.com, arbeitnow and the Getro
boards of German VC funds. Another country means new collectors; another field inside Germany means
new title patterns and search words, which the setup covers.

## How it works

Scripts collect from every source, filter by title, place, repeats and the person's history, and
sort what is left freshest first. The agent then does three things only. It skims the titles and
drops the plainly wrong ones, it reads every remaining posting and gives each a score and a gate, and
it researches the ones it will send: the employer's own apply link, a company note, a headcount.
Scripts check the agent's picks for missed repeats and language lines, render the shortlist and the
per-job packs, and push. The repository is the store the person works from. Email is optional.

The repository is the agent's memory. Every job sent, every job read with its verdict and every
hard rejection are kept under `state/` so no run repeats another's work.

## Setting it up for a person

1. On GitHub, press **Use this template** and create a private repository of your own. Everything the
   radar writes is personal.
2. Open Claude Code in it and say anything. `CLAUDE.md` makes the first session run the setup: it asks
   for the CV and everything else it needs, fills `config/person.md`, generates the profile, the search
   lists and the salary table from it, and stops when `python3 scripts/setup_check.py` prints `READY`.
3. Follow `docs/DEPLOY.md`: the GitHub app, two routines. No mail secrets unless you want email too.

## Layout

| Path | What it is |
|---|---|
| `instructions/PROMPT.md` | the run, step by step; the routine prompt points here |
| `config/person.md` | the one file about the person; filled at setup |
| `instructions/PROFILE.md` | who the person is and how to score; generated from the person file |
| `instructions/COMPANIES.md` | the company boards the collector polls |
| `config/radar.yaml` | search words, title and place filters, ranking weights |
| `scripts/` | collectors, filter, reader, verdict, render, push |
| `state/` | the memory carried between runs; empty in this copy |
| `shortlists/`, `jobs/`, `companies/` | the runs' outputs; empty in this copy |
| `docs/FLOW.md`, `docs/SECURITY.md`, `docs/DEPLOY.md` | the flow, what a run can reach, how to deploy |
| `tests/` | `make ci` runs them; the routine never edits code |

## Rules the runs follow

The agent may not change code during a run. A verdict is refused by the scripts when it breaks a
rule, a job the reader never printed cannot be sent, and the render refuses a list with an unread
fresh job or a missed repeat. The shortlist goes out once per run, from the Action, never from the agent.
