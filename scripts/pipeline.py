#!/usr/bin/env python3
"""The application pipeline ledger.

`pipeline/events.json` is the only source of truth. Every number in `reports/PIPELINE.md`
and in the weekly email is computed from it, so nothing is ever hand-counted.

    pipeline.py add --key lucid-labs --type rejected --company "Lucid Labs" \
                    --role "AI Engineer" --date 2026-09-20 --evidence "..."
    pipeline.py render          rebuild reports/PIPELINE.md
    pipeline.py weekly          print the weekly email body (--end for a past Saturday)
    pipeline.py sync-apps       state/applications.md rows for the week's applied events
    pipeline.py monthly         print the monthly email body
    pipeline.py is-month-end    exit 0 only on the last day of the month
    pipeline.py stats           print the counts
    pipeline.py open            list applications still waiting, oldest first
    pipeline.py followup        the Monday outreach target list, as JSON
    pipeline.py pin             mark an application important, so it leads that list
    pipeline.py unpin           drop the mark

Jobs-found counts come from state/seen.json, which holds one entry per job the radar
has ever emailed, each with the date it was sent.
"""

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import applications as apps_md  # noqa: E402  (the function below is also called applications)

REPO = Path(__file__).resolve().parent.parent
EVENTS = REPO / "pipeline" / "events.json"
SEEN = REPO / "state/seen.json"
LEDGER = REPO / "reports/PIPELINE.md"

# An application with no reply for this many days counts as ghosted. Nothing is
# ever written to say so; it is recomputed on every render from the dates.
GHOST_DAYS = 21

# The Monday outreach list. A chase is worth sending while the requisition is
# still open, so top-ups are ranked newest application first, not oldest. Under a
# week of silence is too early to chase, and past nine weeks the role is filled or
# the search is dead, so neither end is offered.
FOLLOWUP_MIN_SILENT = 7
FOLLOWUP_MAX_SILENT = 63
FOLLOWUP_MAX_TARGETS = 6

TYPES = ("applied", "rejected", "interview", "assessment", "offer", "withdrawn", "closed")
TERMINAL = ("rejected", "offer", "withdrawn", "closed")
ADVANCED = ("interview", "assessment", "offer")


def load():
    return json.loads(EVENTS.read_text())


def save(doc):
    EVENTS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def applications(events):
    """Group events by key and work out where each application stands."""
    by_key = {}
    for e in sorted(events, key=lambda e: (e["date"], TYPES.index(e["type"]))):
        by_key.setdefault(e["key"], []).append(e)

    out = []
    for key, evs in by_key.items():
        first = evs[0]
        applied = next((e["date"] for e in evs if e["type"] == "applied"), None)
        terminal = next((e for e in reversed(evs) if e["type"] in TERMINAL), None)
        advanced = [e for e in evs if e["type"] in ADVANCED]
        last = evs[-1]

        if terminal:
            status = terminal["type"]
        elif advanced:
            status = advanced[-1]["type"]
        else:
            status = "waiting"

        days = None
        if applied and terminal:
            days = (d(terminal["date"]) - d(applied)).days
        elif applied and advanced:
            days = (d(advanced[0]["date"]) - d(applied)).days

        out.append(
            {
                "key": key,
                "company": last.get("company") or first.get("company", ""),
                "role": last.get("role") or first.get("role", ""),
                "track": first.get("track", "ml"),
                "applied": applied,
                "status": status,
                "days": days,
                "events": evs,
                "last_date": last["date"],
            }
        )
    return sorted(out, key=lambda a: (a["applied"] or a["last_date"]))


def silent_days(app, today):
    """Days since the last thing that happened, for an application still waiting."""
    if app["status"] != "waiting" or not app["applied"]:
        return None
    return (today - d(app["last_date"])).days


def jobs_found(start, end):
    """Jobs the radar emailed with a send date in [start, end]."""
    if not SEEN.is_file():
        return 0
    rows = json.loads(SEEN.read_text())
    n = 0
    for r in rows:
        sent = (r.get("sent") or r.get("date") or "")[:10]
        if sent and start.isoformat() <= sent <= end.isoformat():
            n += 1
    return n


def in_window(events, start, end, etype, track="ml"):
    return [
        e
        for e in events
        if e["type"] == etype
        and e.get("track", "ml") == track
        and start.isoformat() <= e["date"] <= end.isoformat()
    ]


def week_bounds(today, week=None):
    """The seven days ending today, or a named ISO week (2026-W37) in full.

    Rolling seven days rather than Monday-to-today on purpose. The digest is sent
    on a Saturday evening, and with a Monday-to-today window anything that arrived
    later that Saturday fell into no digest at all: it is dated in the week just
    reported, while next Saturday's window starts the following Monday. Consecutive
    Saturdays are exactly seven days apart, so this window has no gap and no
    overlap.
    """
    if week:
        y, w = week.upper().split("-W")
        monday = date.fromisocalendar(int(y), int(w), 1)
        return monday, monday + timedelta(days=6)
    return today - timedelta(days=6), today


def last_week_bounds(today, week=None):
    """The ISO week before the one `today` falls in, Monday to Sunday.

    The outreach list is sent on a Monday morning and reports the week that just
    ended, so it uses whole calendar weeks rather than the rolling seven days the
    Saturday digest uses. Run on Monday 22 September this returns 15 to 21
    September. A run that slips to the Tuesday still reports the same week.
    """
    if week:
        y, w = week.upper().split("-W")
        monday = date.fromisocalendar(int(y), int(w), 1)
    else:
        monday = today - timedelta(days=today.weekday() + 7)
    return monday, monday + timedelta(days=6)


def pins(doc):
    """Applications the candidate marked important. Stored on the ledger, never hand-edited."""
    return doc.get("pinned") or []


def pinned_match(pin, app):
    """A pin matches by key, or by company name when the scan chose a different key.

    The key an evening scan invents for a new application cannot be known in advance, so
    a pin set before the application exists would otherwise never bind to it.
    """
    if pin.get("key") and pin["key"] == app["key"]:
        return True
    c = (pin.get("company") or "").strip().lower()
    return bool(c) and c in (app.get("company") or "").lower()


def followup_targets(events, today, week=None, limit=FOLLOWUP_MAX_TARGETS, doc=None):
    """Who to chase this Monday: last week's applications, then older silent ones.

    Anything that already ended is left out. Chasing a company that has already
    said no is the one outcome this list must never produce.
    """
    start, end = last_week_bounds(today, week)
    apps = [a for a in applications(events) if a["track"] == "ml"]
    live = [a for a in apps if a["status"] not in TERMINAL]

    the_pins = pins(doc or {})
    pinned = [a for a in live if any(pinned_match(p, a) for p in the_pins)]
    pinned.sort(key=lambda a: a["applied"] or a["last_date"])
    pinned_keys = {a["key"] for a in pinned}

    fresh = [a for a in live if a["applied"] and start.isoformat() <= a["applied"] <= end.isoformat()
             and a["key"] not in pinned_keys]
    fresh.sort(key=lambda a: a["applied"])

    taken = pinned_keys | {a["key"] for a in fresh}
    topup = [
        a
        for a in live
        if a["key"] not in taken
        and a["status"] == "waiting"
        and a["applied"]
        and FOLLOWUP_MIN_SILENT <= (silent_days(a, today) or 0) <= FOLLOWUP_MAX_SILENT
    ]
    topup.sort(key=lambda a: a["applied"], reverse=True)

    out = []
    for a in pinned + fresh + topup[: max(0, limit - len(pinned) - len(fresh))]:
        out.append(
            {
                "key": a["key"],
                "company": a["company"],
                "role": a["role"],
                "applied": a["applied"],
                "status": a["status"],
                "silent_days": silent_days(a, today),
                "source": ("pinned" if a["key"] in pinned_keys
                           else "last week" if a["key"] in {f["key"] for f in fresh} else "top-up"),
                "why_pinned": next((p.get("why", "") for p in the_pins if pinned_match(p, a)), ""),
                # Verbatim, because the rejection and confirmation mails are where the
                # real names live: Matthew Goddard at Lucid Labs and Jason Hinz at
                # APRIORI both came out of this field. The agent reads them, no regex
                # tries to guess which words are a person.
                "evidence": [
                    {"date": e["date"], "type": e["type"], "text": e.get("evidence", ""), "note": e.get("note", "")}
                    for e in a["events"]
                    if e.get("evidence") or e.get("note")
                ],
            }
        )
    # A pin that binds to nothing is the interesting case, not an error to swallow. It means
    # he marked a role important and no application for it has reached the ledger, which is
    # either that he has not applied yet or that the scan missed it.
    unbound = [p for p in the_pins
               if not any(pinned_match(p, a) for a in applications(events))]
    closed = [dict(p, status=next(a["status"] for a in apps if pinned_match(p, a)))
              for p in the_pins
              if any(pinned_match(p, a) and a["status"] in TERMINAL for a in apps)]
    return {
        "week": f"{start.isocalendar().year}-W{start.isocalendar().week:02d}",
        "window": [start.isoformat(), end.isoformat()],
        "applied_last_week": len(fresh),
        "targets": out,
        "pins_with_no_application": unbound,
        "pins_already_answered": closed,
    }


# ---------------------------------------------------------------- render

def render(doc, today):
    events = doc["events"]
    apps = applications(events)
    ml = [a for a in apps if a["track"] == "ml"]
    side = [a for a in apps if a["track"] != "ml"]

    def count(status, pool=ml):
        return sum(1 for a in pool if a["status"] == status)

    waiting = [a for a in ml if a["status"] == "waiting"]
    ghosted = [a for a in waiting if (silent_days(a, today) or 0) >= GHOST_DAYS]
    live = [a for a in waiting if a not in ghosted]
    replied = [a for a in ml if a["status"] != "waiting"]

    b = doc.get("baseline", {})
    L = []
    L.append("# Application pipeline")
    L.append("")
    L.append(
        "Every application, rejection and interview with its date. "
        "Generated from `pipeline/events.json` by `scripts/pipeline.py render`. "
        "Do not edit this file by hand."
    )
    L.append("")
    L.append(f"Last scan: **{doc.get('last_scan', 'unknown')}**. Rendered: **{today.isoformat()}**.")
    L.append(f"Baseline window: **{b.get('window_start', '?')} to {b.get('window_end', '?')}**, built {b.get('built', '?')}.")
    L.append("")
    L.append("## Where it stands")
    L.append("")
    L.append("| | Count |")
    L.append("|---|---|")
    L.append(f"| Applications (ML and research roles) | {len(ml)} |")
    L.append(f"| Rejected | {count('rejected')} |")
    L.append(f"| Role closed or filled | {count('closed')} |")
    L.append(f"| Interview or assessment reached | {count('interview') + count('assessment')} |")
    L.append(f"| Offers | {count('offer')} |")
    L.append(f"| Still waiting, inside {GHOST_DAYS} days | {len(live)} |")
    L.append(f"| Ghosted, silent {GHOST_DAYS} days or more | {len(ghosted)} |")
    L.append(f"| Side jobs, tracked separately | {len(side)} |")
    L.append("")
    if replied:
        answered = len(replied)
        advanced = count("interview") + count("assessment") + count("offer")
        L.append(
            f"Of {answered} applications that got a real answer, {advanced} reached an "
            f"interview or an assessment."
        )
        L.append("")

    def table(rows, title, note=None):
        L.append(f"## {title}")
        L.append("")
        if note:
            L.append(note)
            L.append("")
        if not rows:
            L.append("None.")
            L.append("")
            return
        L.append("| Applied | Company | Role | Outcome | Date | Days |")
        L.append("|---|---|---|---|---|---|")
        for a in rows:
            last = a["events"][-1]
            outcome = {
                "rejected": "rejected",
                "closed": "role filled or pulled",
                "interview": "interview",
                "assessment": "assessment",
                "offer": "offer",
                "withdrawn": "withdrawn",
                "waiting": "waiting",
            }[a["status"]]
            when = last["date"] if a["status"] != "waiting" else ""
            days = a["days"] if a["days"] is not None else ""
            if a["status"] == "waiting":
                s = silent_days(a, today)
                days = f"{s} silent" if s is not None else ""
            L.append(
                f"| {a['applied'] or 'unknown'} | {a['company']} | {a['role']} | "
                f"{outcome} | {when} | {days} |"
            )
        L.append("")

    table(
        [a for a in ml if a["status"] in ADVANCED],
        "Interviews and assessments",
    )
    table(live, "Waiting", f"Applied, no answer yet, still inside {GHOST_DAYS} days.")
    table(
        ghosted,
        "Ghosted",
        f"Applied, acknowledged in some cases, then silent for {GHOST_DAYS} days or more. "
        "Recomputed on every render, never stored.",
    )
    table([a for a in ml if a["status"] in ("rejected", "closed", "withdrawn")], "Closed out")
    table(side, "Side jobs", "Logistics and retail applications, kept out of the headline counts.")

    L.append("## Speed of rejection")
    L.append("")
    rej = [a for a in ml if a["status"] == "rejected" and a["days"] is not None]
    if rej:
        fast = sorted(rej, key=lambda a: a["days"])
        L.append("| Days | Company | Role |")
        L.append("|---|---|---|")
        for a in fast:
            L.append(f"| {a['days']} | {a['company']} | {a['role']} |")
        L.append("")
        med = sorted(a["days"] for a in rej)[len(rej) // 2]
        L.append(f"Median time to a rejection is {med} days across {len(rej)} rejections with a known application date.")
        L.append("")

    L.append("## How this file is kept")
    L.append("")
    L.append(b.get("method", ""))
    L.append("")
    L.append(f"**Known gaps.** {b.get('known_gaps', '')}")
    L.append("")
    L.append(
        "The radar's evening run scans the mailbox, appends anything new with "
        "`scripts/pipeline.py add`, re-renders this file and pushes. The weekly "
        "summary email goes out on Saturday from `.github/workflows/weekly.yml`."
    )
    LEDGER.write_text("\n".join(L) + "\n")
    render_interviews(doc)
    return len(ml), len(ghosted)


# ---------------------------------------------------------------- reports

def month_bounds(today, month=None):
    """First of the month through today, or a named month (2026-09) in full."""
    if month:
        y, m = (int(x) for x in month.split("-"))
        first = date(y, m, 1)
    else:
        y, m, first = today.year, today.month, today.replace(day=1)
    nxt = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
    last = nxt - timedelta(days=1)
    return first, min(last, today) if month is None else last


def is_month_end(today):
    return (today + timedelta(days=1)).day == 1


def report_body(doc, today, start, end, period="week"):
    events = doc["events"]

    found = jobs_found(start, end)
    applied = in_window(events, start, end, "applied")
    rejected = in_window(events, start, end, "rejected")
    closed = in_window(events, start, end, "closed")
    interviews = in_window(events, start, end, "interview") + in_window(events, start, end, "assessment")

    apps = applications(events)
    ml = [a for a in apps if a["track"] == "ml"]
    waiting = [a for a in ml if a["status"] == "waiting"]
    ghosted = [a for a in waiting if (silent_days(a, today) or 0) >= GHOST_DAYS]

    def span(dt):
        a, b = d(dt[0]) if isinstance(dt[0], str) else dt[0], dt[1]
        return f"{a.strftime('%-d %B')} - {b.strftime('%-d %B')}"

    # This heading is also the email subject: send_mail.py takes the subject from
    # the first `#` line of the file it is given. Changing it changes the subject.
    L = []
    if period == "month":
        L.append(f"# Job Hunt - Monthly Report ({start.strftime('%B %Y')})")
    else:
        L.append(f"# Job Hunt - Weekly Report ({span((start, end))})")
    L.append("")
    L.append(f"The radar found {found} jobs this {period}.")
    L.append(f"You applied to {len(applied)}.")
    L.append(f"{len(rejected)} rejections came back.")
    L.append(f"{len(interviews)} interviews or assessments were reached.")
    L.append(f"{len(ghosted)} applications are ghosted, with no answer in {GHOST_DAYS} days or more.")
    L.append("")

    def block(title, rows, fmt):
        if not rows:
            return
        L.append(f"## {title}")
        L.append("")
        # By date. The sweeps append per event type, so without this a month of
        # rejections reads 1 Sep, 10 Sep, 1 Sep, 3 Sep.
        for e in sorted(rows, key=lambda e: e["date"]):
            L.append(fmt(e))
        L.append("")

    block(
        "Applied",
        applied,
        lambda e: f"- {e['company']}, {e['role']}, {d(e['date']).strftime('%-d %b')}",
    )
    block(
        "Rejections",
        rejected + closed,
        lambda e: f"- {e['company']}, {e['role']}, {d(e['date']).strftime('%-d %b')}",
    )
    block(
        "Interviews and assessments",
        interviews,
        lambda e: f"- {e['company']}, {e['role']}, {d(e['date']).strftime('%-d %b')}"
        + (f". {e['note']}" if e.get("note") else ""),
    )

    # A month end is the point at which the shape of the whole funnel is worth
    # seeing, so the monthly report carries the running totals and the full ghost
    # list. The weekly one stays short on purpose.
    if period == "month":
        rej_all = [a for a in ml if a["status"] == "rejected" and a["days"] is not None]
        L.append("## The whole pipeline so far")
        L.append("")
        L.append(f"{len(ml)} applications on the ledger.")
        L.append(f"{sum(1 for a in ml if a['status'] == 'rejected')} rejected.")
        L.append(
            f"{sum(1 for a in ml if a['status'] in ADVANCED)} reached an interview or an assessment."
        )
        L.append(f"{sum(1 for a in ml if a['status'] == 'offer')} offers.")
        if rej_all:
            med = sorted(a["days"] for a in rej_all)[len(rej_all) // 2]
            L.append(
                f"Median time to a rejection is {med} days, across the {len(rej_all)} "
                f"where the application date is known."
            )
        L.append("")

    L.append("## Still open")
    L.append("")
    L.append(f"{len(waiting)} applications have no answer yet.")
    L.append(f"{len(ghosted)} of those are ghosted.")
    if ghosted and period == "month":
        L.append("")
        for a in ghosted:
            L.append(
                f"- {a['company']}, {a['role']}, applied "
                f"{d(a['applied']).strftime('%-d %B')}, {silent_days(a, today)} days silent"
            )
    elif ghosted:
        oldest = ghosted[0]
        L.append(
            f"The oldest is {oldest['company']}, applied {d(oldest['applied']).strftime('%-d %B')}."
        )
    L.append("")
    L.append("The full ledger with every date is `reports/PIPELINE.md` in the job_radar repo.")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- state/applications.md

# 25 Sep 2026. An application the night run finds in the mailbox also goes into
# state/applications.md, so the radar stops re-sending that job. The radar skips on company
# AND title (filter_run.py), so the title is what matters. A row written here carries
# the job title, never just the company, or a different role there would be hidden.
APPS = REPO / "state/applications.md"
APPS_COLS = apps_md.COLS
MAILBOX_VERDICT = "not researched, found in the mailbox"
NO_ROLE = re.compile(r"not named|unknown|^(n/?a|none|\?)$", re.I)


def _title_hit(a, b):
    """Same job at a company already matched. The night run shortens titles, as in
    "Senior AI Engineer (m/f/d), Semiconductor" for KLA's "Senior AI Engineer (m/f/d),
    Drive Next-Generation Semiconductor Technology", so one title's words sitting inside
    the other's also counts. Needs two words, so "AI Engineer" alone cannot match."""
    from jobid import same_title, norm_title
    if same_title(a, b):
        return True
    ta, tb = set(norm_title(a).split()), set(norm_title(b).split())
    return min(len(ta), len(tb)) >= 2 and (ta <= tb or tb <= ta)


def log_application(company, role, day, location="", evidence=""):
    """Stamp or append the state/applications.md row for one `applied` event. Returns a line
    for the run report. The laptop copy absorbs these through pick.py."""
    from jobid import same_company
    role = (role or "").strip()
    if not role or NO_ROLE.search(role):
        return f"state/applications.md NOT written for {company}: no job title. Find the title and re-run with --role."
    if not APPS.exists():
        return "state/applications.md NOT written: file missing"
    lines = APPS.read_text(encoding="utf-8").split("\n")
    rows = [(i, r) for i, r in ((i, apps_md.parse(l)) for i, l in enumerate(lines)) if r]
    hits = [(i, c) for i, c in rows if same_company(c["Company"], company) and _title_hit(c["Role"], role)]
    if len(hits) > 1:
        from jobid import same_title
        exact = [(i, c) for i, c in hits if same_title(c["Role"], role)]
        hits = exact if len(exact) == 1 else hits
    if len(hits) > 1:
        return (f"state/applications.md NOT written for {company}, '{role}': matches {len(hits)} rows "
                f"({'; '.join(c['Role'] for _, c in hits)}). Stamp the right one by hand.")
    stamp = f"yes {day} (mailbox)"
    if hits:
        i, c = hits[0]
        if c["Applied"].lower().startswith("yes"):
            return f"state/applications.md already says applied: {c['Company']}, {c['Role']}"
        c["Applied"] = stamp
        lines[i] = apps_md.line(c)
        msg = f"state/applications.md stamped applied: {c['Company']}, {c['Role']}"
    else:
        last = max(i for i, _ in rows) if rows else len(lines) - 1
        lines.insert(last + 1, apps_md.line(dict(zip(APPS_COLS, [day, company, role, location, MAILBOX_VERDICT, "", stamp, evidence]))))
        msg = f"state/applications.md row added: {company}, {role}"
    APPS.write_text("\n".join(lines), encoding="utf-8")
    return msg


def sync_apps(doc, start, end):
    """Make sure every `applied` event dated in [start, end] has its state/applications.md row.
    The weekly-report routine runs this, so an application the nightly scan logged
    without a row still reaches the file the radar skips on."""
    return [log_application(e["company"], e.get("role", ""), e["date"], "", e.get("evidence", ""))
            for e in sorted(in_window(doc["events"], start, end, "applied"), key=lambda e: e["date"])]


# ---------------------------------------------------------------- reports/INTERVIEWS.md

# 27 Sep 2026. Every application that reached an interview, a test or an offer, with
# what was sent, and the reply rate by kind of role and by how he applied. Computed
# from the ledger on every render, so it fills itself as the weeks go by.
INTERVIEWS = REPO / "reports/INTERVIEWS.md"

# First match wins, so the narrow families sit above the broad ones.
ROLE_FAMILIES = [
    ("Forward deployed / solutions", r"forward deployed|solutions? engineer|customer engineer"),
    ("Research", r"research|scientist(?!.*data)|wissenschaftl|doctoral|phd"),
    ("Computer vision / perception", r"vision|perception|imaging|biometric|3d|geometry"),
    ("Audio / speech / voice", r"audio|speech|voice"),
    ("Robotics / RL", r"robot|reinforcement|autonomous"),
    ("Data science", r"data scien|statistic|analyst"),
    ("MLOps / platform / data eng", r"mlops|platform|infrastructure|data engineer|inference"),
    ("LLM / agents / applied AI", r"llm|agent|genai|generative|applied ai|\bai\b|ki[/ -]"),
    ("ML engineer", r"machine learning|\bml\b"),
]


def role_family(role):
    r = (role or "").lower()
    return next((name for name, rx in ROLE_FAMILIES if re.search(rx, r)), "Other")


def channel(app):
    """How he applied, read from the sender of the confirmation mail."""
    ev = next((e.get("evidence", "") for e in app["events"] if e["type"] == "applied"), "").lower()
    for name, rx in (("LinkedIn", r"linkedin"), ("join.com", r"join\.com"),
                     ("Greenhouse", r"greenhouse"), ("Ashby", r"ashby"), ("Lever", r"lever\.co"),
                     ("Personio", r"personio"), ("Workday", r"workday|myworkday"),
                     ("SmartRecruiters", r"smartrecruiters"), ("Recruitee", r"recruitee"),
                     ("StepStone", r"stepstone"), ("XING", r"xing"),
                     ("SuccessFactors", r"successfactors"), ("softgarden", r"softgarden"),
                     ("Workable", r"workable"), ("Teamtailor", r"teamtailor"),
                     ("HireHive", r"hirehive"), ("Clera", r"getclera"),
                     ("Recruiter", r"recruit(?!ee)|talent|agency")):
        if re.search(rx, ev):
            return name
    # pick.py batches say only that he applied, not where
    if not ev or ev.startswith("applied by anas"):
        return "Not recorded"
    return "Company site or email"


def apps_row(company, role):
    """His state/applications.md row for this job, for the CV used and the fit he was given."""
    from jobid import same_company
    if not APPS.exists():
        return {}
    for c in apps_md.rows(APPS):
        if same_company(c["Company"], company) and _title_hit(c["Role"], role):
            return c
    return {}


def render_interviews(doc):
    apps = [a for a in applications(doc["events"]) if a["track"] == "ml" and a["applied"]]
    hot = [a for a in apps if any(e["type"] in ADVANCED for e in a["events"])]
    L = ["# Interviews and tests", "",
         "Computed by `scripts/pipeline.py render` from `pipeline/events.json`. Never edit by hand.", "",
         f"{len(hot)} of {len(apps)} applications reached an interview, a test or an offer.", ""]
    L += ["| Applied | Company | Role | Kind of role | Applied through | First answer | Days | Stages | Fit given | Docs sent |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for a in sorted(hot, key=lambda a: a["applied"], reverse=True):
        adv = [e for e in a["events"] if e["type"] in ADVANCED]
        row = apps_row(a["company"], a["role"])
        L.append("| " + " | ".join(x.replace("|", "/") for x in (
            a["applied"], a["company"], a["role"], role_family(a["role"]), channel(a),
            adv[0]["date"], str((d(adv[0]["date"]) - d(a["applied"])).days),
            ", ".join(f"{e['type']} {e['date']}" for e in adv),
            row.get("Verdict", ""), row.get("Docs built", ""))) + " |")
    for title, keyf in (("By kind of role", lambda a: role_family(a["role"])),
                        ("By how he applied", channel)):
        groups = {}
        for a in apps:
            groups.setdefault(keyf(a), []).append(a)
        L += ["", f"## {title}", "",
              "| | Applied | Interview or test | Rate | Rejected | Still waiting |", "|---|---|---|---|---|---|"]
        for k, g in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            h = sum(1 for a in g if a in hot)
            L.append(f"| {k} | {len(g)} | {h} | {100 * h // len(g)}% | "
                     f"{sum(1 for a in g if a['status'] == 'rejected')} | "
                     f"{sum(1 for a in g if a['status'] == 'waiting')} |")
    INTERVIEWS.write_text("\n".join(L) + "\n", encoding="utf-8")
    return len(hot)


# ---------------------------------------------------------------- cli

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="append one event and re-render")
    a.add_argument("--key", required=True, help="stable slug for the application, e.g. lucid-labs")
    a.add_argument("--type", required=True, choices=TYPES)
    a.add_argument("--company", required=True)
    a.add_argument("--role", default="")
    a.add_argument("--date", required=True, help="YYYY-MM-DD, the date on the email")
    a.add_argument("--track", default="ml", choices=["ml", "side"])
    a.add_argument("--evidence", default="", help="sender and the phrase that decided it")
    a.add_argument("--note", default="")
    a.add_argument("--location", default="", help="applied only: city for a new state/applications.md row")

    sub.add_parser("render", help="rebuild reports/PIPELINE.md")
    sub.add_parser("stats", help="print the counts")
    sub.add_parser("open", help="list applications still waiting, oldest first")

    w = sub.add_parser("weekly", help="print the weekly email body")
    w.add_argument("--week", help="ISO week such as 2026-W37, default is the seven days ending today")
    w.add_argument("--end", help="YYYY-MM-DD, the last day of the seven-day window, default today")
    w.add_argument("--out", help="write to this path instead of stdout")

    sub.add_parser("report-end", help="the most recent Saturday on or before today, and its ISO week")

    sa = sub.add_parser("sync-apps", help="write the state/applications.md row for every applied event in a window")
    sa.add_argument("--end", help="YYYY-MM-DD, the last day of the seven-day window, default today")

    mo = sub.add_parser("monthly", help="print the monthly email body")
    mo.add_argument("--month", help="a month such as 2026-09, default is the month containing today")
    mo.add_argument("--out", help="write to this path instead of stdout")

    s = sub.add_parser("scanned", help="stamp the last_scan date")
    s.add_argument("--date", required=True)

    f = sub.add_parser("followup", help="the Monday outreach target list, as JSON")
    f.add_argument("--week", help="ISO week such as 2026-W38, default is the week before this one")
    f.add_argument(
        "--max",
        type=int,
        default=FOLLOWUP_MAX_TARGETS,
        help="how many companies to aim for; last week's own applications are never dropped",
    )
    f.add_argument("--out", help="write to this path instead of stdout")

    pn = sub.add_parser("pin", help="mark an application important, so it leads the Monday list")
    pn.add_argument("--key", default="", help="the ledger key, when the application already exists")
    pn.add_argument("--company", default="", help="company name, used when the key is not known yet")
    pn.add_argument("--why", default="", help="one line, printed in the email")

    up = sub.add_parser("unpin", help="drop the mark")
    up.add_argument("--key", default="")
    up.add_argument("--company", default="")

    sub.add_parser("is-month-end", help="exit 0 only if today is the last day of the month")

    args = p.parse_args()
    doc = load()
    today = date.today()

    if args.cmd == "add":
        ev = {
            "key": args.key,
            "date": args.date,
            "type": args.type,
            "company": args.company,
            "role": args.role,
            "track": args.track,
        }
        if args.evidence:
            ev["evidence"] = args.evidence
        if args.note:
            ev["note"] = args.note
        dupe = [
            e
            for e in doc["events"]
            if e["key"] == args.key and e["type"] == args.type and e["date"] == args.date
        ]
        if dupe:
            print(f"already recorded: {args.key} {args.type} {args.date}, nothing written")
            if args.type == "applied":
                print(log_application(args.company, args.role, args.date, args.location, args.evidence))
            return 0
        doc["events"].append(ev)
        save(doc)
        render(doc, today)
        print(f"added {args.key} {args.type} {args.date}")
        if args.type == "applied":
            print(log_application(args.company, args.role, args.date, args.location, args.evidence))
        return 0

    if args.cmd == "report-end":
        # Saturday is weekday 5. Run on a Saturday this is today; a catch-up run on a
        # Sunday reports the Saturday just gone, so a missed week is never skipped.
        end = today - timedelta(days=(today.weekday() - 5) % 7)
        y, w, _ = end.isocalendar()
        print(f"{end.isoformat()} {y}-W{w:02d}")
        return 0

    if args.cmd == "sync-apps":
        start, end = week_bounds(d(args.end) if args.end else today)
        lines = sync_apps(doc, start, end)
        print("\n".join(lines) or f"no applied events between {start} and {end}")
        return 0

    if args.cmd == "scanned":
        doc["last_scan"] = args.date
        save(doc)
        render(doc, today)
        print(f"last_scan = {args.date}")
        return 0

    if args.cmd == "render":
        n, g = render(doc, today)
        print(f"reports/PIPELINE.md written, {n} applications, {g} ghosted")
        return 0

    if args.cmd == "is-month-end":
        print("yes" if is_month_end(today) else "no")
        return 0 if is_month_end(today) else 1

    if args.cmd in ("weekly", "monthly"):
        if args.cmd == "monthly":
            start, end = month_bounds(today, args.month)
            body = report_body(doc, today, start, end, period="month")
        else:
            if args.end:
                today = d(args.end)
            start, end = week_bounds(today, args.week)
            body = report_body(doc, today, start, end, period="week")
        if args.out:
            Path(args.out).write_text(body)
            print(args.out)
        else:
            sys.stdout.write(body)
        return 0

    if args.cmd == "pin":
        if not (args.key or args.company):
            print("pin needs --key or --company", file=sys.stderr)
            return 2
        doc.setdefault("pinned", [])
        for p_ in doc["pinned"]:
            if (args.key and p_.get("key") == args.key) or \
               (args.company and (p_.get("company") or "").lower() == args.company.lower()):
                p_["why"] = args.why or p_.get("why", "")
                save(doc)
                print("already pinned: %s" % (p_.get("company") or p_.get("key")))
                return 0
        doc["pinned"].append({k: v for k, v in
                              (("key", args.key), ("company", args.company),
                               ("why", args.why), ("since", today.isoformat())) if v})
        save(doc)
        print("pinned %s" % (args.company or args.key))
        return 0

    if args.cmd == "unpin":
        before = len(doc.get("pinned") or [])
        doc["pinned"] = [p_ for p_ in doc.get("pinned") or []
                         if not ((args.key and p_.get("key") == args.key)
                                 or (args.company and (p_.get("company") or "").lower() == args.company.lower()))]
        save(doc)
        print("unpinned %d" % (before - len(doc["pinned"])))
        return 0

    if args.cmd == "followup":
        doc_out = followup_targets(doc["events"], today, args.week, args.max, doc)
        text = json.dumps(doc_out, indent=2, ensure_ascii=False) + "\n"
        if args.out:
            Path(args.out).write_text(text)
            print(args.out)
        else:
            sys.stdout.write(text)
        return 0

    if args.cmd == "open":
        for a in applications(doc["events"]):
            if a["track"] == "ml" and a["status"] == "waiting":
                print(f"{a['applied']}  {silent_days(a, today):>3}d  {a['company']} — {a['role']}")
        return 0

    if args.cmd == "stats":
        apps = applications(doc["events"])
        ml = [a for a in apps if a["track"] == "ml"]
        waiting = [a for a in ml if a["status"] == "waiting"]
        ghosted = [a for a in waiting if (silent_days(a, today) or 0) >= GHOST_DAYS]
        print(f"applications (ml):  {len(ml)}")
        for st in ("waiting", "rejected", "closed", "interview", "assessment", "offer"):
            print(f"  {st:<11} {sum(1 for a in ml if a['status'] == st)}")
        print(f"  ghosted     {len(ghosted)}")
        print(f"side jobs:          {sum(1 for a in apps if a['track'] != 'ml')}")
        start, end = week_bounds(today)
        print(f"this week {start} to {end}: {jobs_found(start, end)} jobs found")
        for p_ in pins(doc):
            who = p_.get("company") or p_.get("key")
            bound = any(pinned_match(p_, a) for a in apps)
            print(f"pinned: {who}{'' if bound else '  (no application on the ledger yet)'}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
