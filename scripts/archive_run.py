#!/usr/bin/env python3
"""Keep the run's working files as a GitHub Release, so a discard or a verdict can be audited later.

Added 31 Oct 2026. The scratch folder is deleted with the cloud machine, so until now nothing
showed what a run saw: the text-twin drops, the triage list, the batches the reader printed, the
verdicts. Each run now uploads one zip to a release tagged `run-<date>-<slot>`.

    python3 scripts/archive_run.py $SC        after gitsync.py push; prints one line, never fails the run

What goes in: every file under $SC except the raw collector files (`<source>.json`, 23,000 rows a
run, 17 MB) and the fetch caches (`*_read.json`). In their place `cards.json` lists every collected
row with six fields (source, company, title, location, date, url), about 3.5 MB, which is enough to
see what the title and location cut threw out. Releases older than KEEP_DAYS are deleted.

Needs `RADAR_GITHUB_TOKEN` in the environment, a fine-grained token with Contents read and write on
the repo (docs/SETUP_NOTES.md). Without it the script prints `archive: skipped` and exits 0.
"""
import datetime
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile

REPO = os.environ.get("RADAR_REPO", "AnasYasin/job_radar")
API = "https://api.github.com"
KEEP_DAYS = 90
SOURCES = ("ba", "ats", "getro", "talent", "arbeitnow", "linkedin", "xing", "stepstone")
CARD_FIELDS = ("company", "title", "location", "date", "url")


def cards(sc):
    """One compact row per collected row, across the eight raw files."""
    out = []
    for src in SOURCES:
        try:
            rows = json.load(open(os.path.join(sc, src + ".json"), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for j in rows if isinstance(rows, list) else []:
            if isinstance(j, dict):
                out.append(dict(source=src, **{k: j.get(k, "") for k in CARD_FIELDS}))
    return out


def _skip(name):
    base = os.path.basename(name)
    return (base.endswith(".json") and base[:-5] in SOURCES) or base.endswith("_read.json")


def bundle(sc):
    """The zip as bytes: cards.json plus every working file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("cards.json", json.dumps(cards(sc), ensure_ascii=False))
        for root, _, files in os.walk(sc):
            for f in sorted(files):
                p = os.path.join(root, f)
                if not _skip(p):
                    z.write(p, os.path.relpath(p, sc))
    return buf.getvalue()


def _call(token, method, url, data=None, ctype="application/json"):
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=120) as r:
        body = r.read()
    return json.loads(body) if body.strip() else {}


def upload(sc, token, today=None):
    """Create the release and attach the zip. Returns the one-line summary."""
    slot = json.load(open(os.path.join(sc, "run_slot.json"), encoding="utf-8"))
    tag = "run-%s-%s" % (slot["date"], slot["slot"])
    try:
        sl = json.load(open(os.path.join(sc, "shortlist.json"), encoding="utf-8"))
        cov = sl.get("coverage") or {}
        body = "%s %s: %s candidates, %s read in full, %d sent" % (
            slot["date"], slot["slot"], cov.get("candidates", "?"), cov.get("read_full", "?"), len(sl.get("jobs") or []))
    except (OSError, ValueError, AttributeError):
        body = "%s %s" % (slot["date"], slot["slot"])
    data = bundle(sc)
    # 31 Oct 2026: a reply lost on the way back (reset, timeout) leaves the release created and the
    # retry answering 422 already_exists. Look for the tag first, so a rerun attaches to it.
    try:
        rel = _call(token, "GET", "%s/repos/%s/releases/tags/%s" % (API, REPO, tag))
    except urllib.error.HTTPError as ex:
        if ex.code != 404:
            raise
        rel = _call(token, "POST", "%s/repos/%s/releases" % (API, REPO),
                    json.dumps(dict(tag_name=tag, name=tag, body=body, prerelease=True)).encode())
    up = rel["upload_url"].split("{", 1)[0] + "?name=" + tag + ".zip"
    try:
        _call(token, "POST", up, data, "application/zip")
    except OSError as ex:
        # 31 Oct 2026: the first real upload stored the asset and then the reply timed out. The
        # asset is the fact; look for it before calling the upload a failure.
        got = _call(token, "GET", "%s/repos/%s/releases/%s" % (API, REPO, rel["id"]))
        if not any(a.get("name") == tag + ".zip" for a in got.get("assets") or []):
            raise ex
    return "archive: %s, %d KB, %s" % (tag, len(data) // 1024, prune(token, today))


def prune(token, today=None):
    """Delete run releases older than KEEP_DAYS. Returns a short count."""
    today = today or datetime.date.today()
    cut = (today - datetime.timedelta(days=KEEP_DAYS)).isoformat()
    n = 0
    for r in _call(token, "GET", "%s/repos/%s/releases?per_page=100" % (API, REPO)):
        tag = r.get("tag_name") or ""
        if tag.startswith("run-") and (r.get("created_at") or "")[:10] < cut:
            _call(token, "DELETE", "%s/repos/%s/releases/%s" % (API, REPO, r["id"]))
            _call(token, "DELETE", "%s/repos/%s/git/refs/tags/%s" % (API, REPO, tag))
            n += 1
    return "%d old release%s deleted" % (n, "" if n == 1 else "s")


def main(sc):
    token = os.environ.get("RADAR_GITHUB_TOKEN", "").strip()
    if not token:
        print("archive: skipped, no RADAR_GITHUB_TOKEN")
        return 0
    try:
        print(upload(sc, token))
    except Exception as ex:  # the archive must never fail the run
        msg = ex.read().decode(errors="replace")[:200] if isinstance(ex, urllib.error.HTTPError) else str(ex)[:200]
        print("archive: failed, %s" % msg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
