# Security

Written 7 Oct 2026. What a cloud run can reach, what could go wrong, and what guards it.

## What a run can reach

A routine run is a fresh cloud machine. It clones this repo, reads job pages on the open web, and pushes
its results back here.

- **This repo, read and write.** The Claude GitHub App is installed on `AnasYasin/job_radar` only
  (github.com/settings/installations, "Only select repositories"). Other private repos are out of reach.
- **Public repos, read only.** Anyone can read those anyway.
- **The open web.** The `job_hunt` environment has Full network access, because the radar reads hundreds of
  career pages.
- **No connectors.** Gmail is not attached. A run cannot read the mailbox.

A run cannot reach the laptop, the Claude account, or GitHub Secrets.

## The risk

Any job page can hide text written to steer the agent. This is called prompt injection. A tricked run could
do two harmful things.

1. Send the repo's contents to an outside address. That exposes `state/applications.md` and
   `state/contacts.md`.
2. Edit a file in `.github/workflows/` so that the next email delivery leaks the `GMAIL_APP_PASSWORD` secret.

A guard inside a workflow cannot stop the second one. The same run could delete the guard or add a new
workflow. Blocking pushes to `.github/` needs GitHub branch rules, which a private repo only gets on GitHub
Pro.

## The guards

1. **Repo access limited to this repo.** Set on the Claude GitHub App.
2. **No Gmail connector on the routines.** Keep it that way. With Gmail attached, a tricked run could read
   reset links and login codes from the whole mailbox.
3. **An alert when a workflow changes.** The laptop's `~/job_hunt/scripts/radar_autopull.sh` pulls every 30
   minutes. When a pulled commit changes anything under `.github/`, it writes `WORKFLOW CHANGED BY A PULL` to
   `~/.cache/radar-autopull.log` and shows a critical desktop alert. Runs never need to touch `.github/`, so
   every such alert is worth a look. The laptop is out of a run's reach.
4. **A sender account with nothing in it (recommended, not done yet).** Create a separate Gmail account only
   for sending the radar email. Put its address and app password in the repo secrets `GMAIL_ADDRESS` and
   `GMAIL_APP_PASSWORD`. If the password leaks, the attacker gets an empty mailbox.

## If the alert fires

1. Open the commit on GitHub and read the change to `.github/workflows/`.
2. If you did not make it, revoke the app password at myaccount.google.com/apppasswords.
3. Revert the commit, then set a new app password in the repo secrets.
