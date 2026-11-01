# job-radar

A scheduled cloud agent that finds jobs for one person and sends a ranked shortlist. It finds and
ranks. It never applies. README.md says how it works, docs/FLOW.md says what a run does step by step.

## First thing in every session

Run `python3 scripts/setup_check.py`. If it prints anything but `READY`, this copy is not set up for
a person yet. Read SETUP.md and do what it says, whatever the person's first message was: ask for
the CV, fill `config/person.md`, run `python3 scripts/setup_gen.py`, check again. Do not start a run,
do not push, do not change the scripts during setup.

When it prints `READY`, the repository is in use. docs/DEPLOY.md covers the routines and the first
run.

## Rules that always hold

- `config/person.md` is the one file that describes the person. `instructions/PROFILE.md`, the
  `profile` and `search` lists in `config/radar.yaml` and the `ASK` table in `scripts/salary.py` are
  generated from it by `scripts/setup_gen.py`. Edit the person file and generate; never edit the
  outputs by hand.
- `instructions/COMPANIES.md` is the one list of company boards. Add a line only with a slug tested
  against the live board.
- The scheduled runs follow `instructions/PROMPT.md` and never change code. Code changes happen in
  a session like this one, with `make ci` green before any push.
- Times shown to the person are in their time zone. Crons and the slot rule in `scripts/slots.py`
  are UTC.
