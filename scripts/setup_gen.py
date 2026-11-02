#!/usr/bin/env python3
"""Generate the person-specific files from config/person.md (1 Nov 2026).

    python3 scripts/setup_gen.py [--root <repo>]

Reads config/person.md, one heading per answer (the file says what goes under each), and writes:

    instructions/PROFILE.md     rendered from instructions/PROFILE.template.md; each <fill: ...>
                                marker, in order, becomes the matching answer
    config/radar.yaml           profile.name, profile.referral_companies, profile.applied_companies
                                and every list under search.<site>; nothing else in the file moves
    scripts/salary.py           the four figures in the ASK table

Run it again after every change to the person file; it overwrites those outputs. Then run
scripts/setup_check.py until it prints READY. The person file is the source; the outputs are not
edited by hand.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The <fill: ...> markers of the template, in order, and the person.md heading each one takes.
MARKERS = ["Name", "Who the candidate is", "Experience", "Flagship projects", "Tools really used", "Target roles",
           "Location rules", "Language level", "Seniority", "Referral companies", "Applied before", "Never send"]
SITES = {"linkedin": ("roles", "places"), "bundesagentur": ("queries", "places"), "xing": ("queries", "places"),
         "stepstone": ("roles", "cities"), "talent": ("roles", "cities")}
HINT = re.compile(r"^\*.*?\*$", re.S)


def read_person(path):
    """{heading: body} with the italic hint removed; a body is the text, lists stay as lines."""
    out, head, body = {}, None, []
    for line in open(path, encoding="utf-8").read().splitlines():
        if line.startswith("## "):
            if head is not None:
                out[head] = _body(body)
            head, body = line[3:].strip(), []
        elif head is not None:
            body.append(line)
    if head is not None:
        out[head] = _body(body)
    return out


def _body(lines):
    text = "\n".join(lines).strip()
    # the hint is one italic paragraph; it is removed whole, wherever it sits
    text = re.sub(r"(?s)(?:^|\n\n)\*[^*]+\*(?=\n\n|$)", "", text).strip()
    return text


def items(text):
    """The bullet lines of a section as a list, minus empty ones; a bare `''` means an empty string."""
    out = []
    for l in (text or "").splitlines():
        l = l.strip()
        if l.startswith("- ") or l == "-":
            v = l[1:].strip()
            if v in ("''", '""'):
                out.append("")
            elif v:
                out.append(v)
    return out


def render_profile(template, person):
    fills = iter(MARKERS)
    missing = []

    def one(m):
        key = next(fills)
        val = person.get(key, "").strip()
        if key == "Applied before":
            val = ", ".join(items(val)) or "none"
        if not val:
            if key != "Flagship projects":          # optional; the section is removed below
                missing.append(key)
            return m.group(0)
        return val
    out = re.sub(r"<fill:.*?>", one, template, flags=re.S)
    if not person.get("Flagship projects", "").strip():
        out = re.sub(r"\n## Flagship projects\n.*?(?=\n## )", "", out, flags=re.S)
    return out, missing


def set_list(lines, start, end, key, values, indent):
    """Replace `key: []` or `key:` + its `- ` items between start and end with `values`. Returns the new end."""
    pad = " " * indent
    for i in range(start, end):
        if re.match(r"^%s%s:\s*(\[\]\s*)?$" % (pad, re.escape(key)), lines[i]):
            j = i + 1
            while j < end and re.match(r"^%s- " % pad, lines[j]):
                j += 1
            new = ["%s%s:%s" % (pad, key, " []" if not values else "")] + ["%s- %s" % (pad, _yaml(v)) for v in values]
            lines[i:j] = new
            return end + len(new) - (j - i)
    raise SystemExit("config/radar.yaml: no line `%s%s:` to fill" % (pad, key))


def _yaml(v):
    if v == "":
        return "''"
    return "'%s'" % v.replace("'", "''") if re.search(r"[:#\[\]{}'\"\\]|^\s|\s$|^(no|on|yes|off|true|false|null)$", v, re.I) else v


def write_config(path, person):
    lines = open(path, encoding="utf-8").read().split("\n")
    n = len(lines)
    name = person.get("Name", "").strip().replace('"', "'")
    for i, l in enumerate(lines):
        if re.match(r'^  name:\s*".*"\s*$', l):
            lines[i] = '  name: "%s"' % name
            break
    else:
        raise SystemExit("config/radar.yaml: no profile.name line")
    n = set_list(lines, 0, n, "referral_companies", items(person.get("Referral patterns", "")), 2)
    n = set_list(lines, 0, n, "applied_companies", [v.lower() for v in items(person.get("Applied before", ""))], 2)
    s = next(i for i, l in enumerate(lines) if l == "search:")
    for site, keys in SITES.items():
        a = next(i for i in range(s, n) if lines[i] == "  %s:" % site)
        b = next((i for i in range(a + 1, n) if re.match(r"^\S", lines[i]) or re.match(r"^  \w+:$", lines[i])), n)
        for k in keys:
            vals = items(person.get("Search %s %s" % (site, k), ""))
            b = set_list(lines, a, b, k, vals, 4)
        n = len(lines)
    open(path, "w", encoding="utf-8").write("\n".join(lines))


def write_salary(path, person):
    figs = {}
    for v in items(person.get("Salary", "")):
        k, _, f = v.partition(":")
        figs[k.strip().lower()] = f.strip()
    t = open(path, encoding="utf-8").read()
    for k in ("startup", "mid", "large", "public"):
        t, c = re.subn(r'("%s": \()"[^"]*",' % k, r'\1"%s",' % figs.get(k, "").replace("\\", "\\\\"), t, count=1)
        if c != 1:
            raise SystemExit("scripts/salary.py: ASK has no %s line" % k)
    open(path, "w", encoding="utf-8").write(t)


def main(root=ROOT):
    person = read_person(os.path.join(root, "config", "person.md"))
    template = open(os.path.join(root, "instructions", "PROFILE.template.md"), encoding="utf-8").read()
    profile, missing = render_profile(template, person)
    open(os.path.join(root, "instructions", "PROFILE.md"), "w", encoding="utf-8").write(profile)
    write_config(os.path.join(root, "config", "radar.yaml"), person)
    write_salary(os.path.join(root, "scripts", "salary.py"), person)
    for key in missing:
        print("person.md: nothing under '%s' yet; the marker stays in PROFILE.md" % key)
    print("generated instructions/PROFILE.md, config/radar.yaml (profile, search), scripts/salary.py (ASK)")
    return 0


if __name__ == "__main__":
    root = sys.argv[sys.argv.index("--root") + 1] if "--root" in sys.argv else ROOT
    sys.exit(main(root))
