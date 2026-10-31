#!/usr/bin/env python3
"""One JSON per company under companies/, written by both sides.

The cloud run fills an entry when it already has the employer's page open (write_pack.py calls
`upsert` for every job it sends). The laptop tops it up during research (`pick.py` prints the
entry, the job_hunt session writes back with `set`). Git carries it both ways; pick.py commits
the directory together with state/applications.md.

    company_cache.py get "Audatic"                       print the entry, or "none"
    company_cache.py set "Audatic" what="..." size="..." ml_team="..." funding="..." notes="..."
    company_cache.py set "Audatic" --json '{"site": "...", "board": "ashby:audatic"}'
    company_cache.py list                                one line per company, newest first

Fields (all optional, all strings unless noted): name, aliases (list), site, careers_url, board
(kind:slug), what, users, size, stage, funding, ml_team, language, notes, sources (list),
last_seen (date the radar last sent a job here), sent (list of {date, title, fit, priority}),
updated, updated_by (cloud|laptop).
"""
import datetime, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "companies")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from jobid import norm_company

LEGAL = re.compile(r"\b(gmbh|ag|se|kg|inc|ltd|llc|group|holding|e\.?v\.?)\b", re.I)


def slug(name):
    n = re.sub(r"\(.*?\)", " ", name or "")
    n = LEGAL.sub(" ", norm_company(n) if callable(norm_company) else n.lower())
    n = re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")
    return n[:60] or "unknown"


def path(name):
    return os.path.join(DIR, slug(name) + ".json")


def get(name):
    p = path(name)
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    # alias search
    if os.path.isdir(DIR):
        s = slug(name)
        for f in os.listdir(DIR):
            try:
                d = json.load(open(os.path.join(DIR, f), encoding="utf-8"))
            except Exception:
                continue
            if s in [slug(a) for a in d.get("aliases", [])]:
                return d
    return None


def upsert(name, fields, by="cloud"):
    os.makedirs(DIR, exist_ok=True)
    d = get(name) or {"name": name, "aliases": [], "sent": [], "sources": []}
    if name not in d.get("aliases", []) and name != d.get("name"):
        d.setdefault("aliases", []).append(name)
    for k, v in fields.items():
        if v in (None, "", [], {}):
            continue
        if k == "sent":
            for row in (v if isinstance(v, list) else [v]):
                if row not in d.setdefault("sent", []):
                    d["sent"].append(row)
        elif k in ("aliases", "sources"):
            for x in (v if isinstance(v, list) else [v]):
                if x not in d.setdefault(k, []):
                    d[k].append(x)
        elif k in ("what", "users", "notes") and d.get(k) and d[k] != v and by == "cloud" and len(d[k]) >= len(v):
            continue            # the laptop's longer research note wins over a shorter cloud note
        else:
            d[k] = v
    d["updated"] = datetime.date.today().isoformat()
    d["updated_by"] = by
    json.dump(d, open(path(d.get("name") or name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return d


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("get", "set", "list"):
        print(__doc__)
        return
    if a[0] == "list":
        rows = []
        for f in os.listdir(DIR) if os.path.isdir(DIR) else []:
            d = json.load(open(os.path.join(DIR, f), encoding="utf-8"))
            rows.append((d.get("updated", ""), d.get("name", f), d.get("board", ""), (d.get("what") or "")[:70]))
        for r in sorted(rows, reverse=True):
            print("%s  %-30s %-22s %s" % r)
        return
    name = a[1]
    if a[0] == "get":
        d = get(name)
        print(json.dumps(d, ensure_ascii=False, indent=1) if d else "none")
        return
    fields = {}
    rest = a[2:]
    if rest and rest[0] == "--json":
        fields = json.loads(rest[1])
    else:
        for kv in rest:
            k, _, v = kv.partition("=")
            fields[k] = v
    d = upsert(name, fields, by="laptop")
    print("saved", path(d.get("name") or name))


if __name__ == "__main__":
    main()
