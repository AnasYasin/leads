#!/usr/bin/env python3
"""A small reader for the block YAML that config/radar.yaml is written in. Added 29 Sep 2026.

cfg.py uses PyYAML when it is installed and this otherwise, so a cloud image without PyYAML still
runs the radar (review, 29 Sep 2026: installing PyYAML with pip from each collector at once could
fail). It reads exactly what PyYAML's safe_dump writes for this file, and gives the same result as
yaml.safe_load, which tests/test_minyaml.py checks on the real file and on thousands of generated
ones. Anything outside that subset raises ValueError naming the line, and never guesses:

    supported   nested mappings, block lists (indented or not), lists of mappings, comments,
                plain, 'single' and "double" quoted scalars on one line, ints, true/false and the
                other YAML 1.1 booleans, null, and an empty list or mapping written [] or {}
    refused     flow style ([a, b] or {a: b}), anchors and aliases, tags, block scalars (| or >),
                a scalar wrapped onto a second line, plain scalars PyYAML would read as a float,
                a date or a time, tabs in indentation
"""
import re

_BOOL = {"yes": True, "true": True, "on": True, "no": False, "false": False, "off": False}
_BOOL_FORMS = {w for k in _BOOL for w in (k, k.capitalize(), k.upper())}
_NULL = {"~", "null", "Null", "NULL", ""}
_INT = re.compile(r"^[-+]?(0|[1-9][0-9]*)$")
# Plain scalars PyYAML resolves to something other than a string or an int, and this reader does not.
_OTHER = re.compile(r"^(?:[-+]?(?:\.[0-9]+|[0-9][0-9_]*)(?:\.[0-9_]*)?(?:[eE][-+]?[0-9]+)?"   # float
                    r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN)"                              # inf, nan
                    r"|[-+]?0[0-7_]+|[-+]?0x[0-9a-fA-F_]+|[-+]?0b[01_]+|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+"
                    r"|[-+]?[1-9][0-9_]+|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}.*|=|<<)$")
_DQ_ESC = {"0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v", "f": "\f",
           "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\", "N": "\x85",
           "_": "\xa0", "L": " ", "P": " "}


class _Line:
    def __init__(self, no, indent, text):
        self.no, self.indent, self.text = no, indent, text


def _err(line, msg):
    raise ValueError("config line %d: %s (%r)" % (line.no, msg, line.text[:60]))


def _lines(text):
    out = []
    for no, raw in enumerate(text.split("\n"), 1):
        body = raw.rstrip()
        if not body.strip() or body.lstrip().startswith("#"):
            continue
        if "\t" in body[:len(body) - len(body.lstrip())]:
            raise ValueError("config line %d: tab in indentation" % no)
        if body.strip() in ("---", "..."):
            raise ValueError("config line %d: document markers are not supported" % no)
        out.append(_Line(no, len(body) - len(body.lstrip(" ")), body.strip()))
    return out


def _single(line, s):
    """'...' with '' for a quote. Returns (value, rest)."""
    i, out = 1, []
    while i < len(s):
        if s[i] == "'":
            if s[i + 1:i + 2] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), s[i + 1:]
        out.append(s[i])
        i += 1
    _err(line, "unclosed single quote (a quoted value wrapped onto the next line?)")


def _double(line, s):
    i, out = 1, []
    while i < len(s):
        c = s[i]
        if c == '"':
            return "".join(out), s[i + 1:]
        if c == "\\":
            e = s[i + 1:i + 2]
            if e in _DQ_ESC:
                out.append(_DQ_ESC[e])
                i += 2
                continue
            n = {"x": 2, "u": 4, "U": 8}.get(e)
            h = s[i + 2:i + 2 + n] if n else ""
            if not n or len(h) != n or not re.fullmatch(r"[0-9a-fA-F]+", h):
                _err(line, "unsupported escape \\%s" % e)
            out.append(chr(int(h, 16)))
            i += 2 + n
            continue
        out.append(c)
        i += 1
    _err(line, "unclosed double quote (a quoted value wrapped onto the next line?)")


def _scalar(line, s):
    s = s.strip()
    if s.startswith("'") or s.startswith('"'):
        v, rest = (_single if s[0] == "'" else _double)(line, s)
        rest = rest.strip()
        if rest and not rest.startswith("#"):
            _err(line, "text after a quoted value")
        return v
    if s in ("[]", "{}"):                          # an emptied list or mapping, as PyYAML writes it
        return [] if s == "[]" else {}
    if s[:1] in ("[", "{"):
        _err(line, "flow style ([...] or {...}) is not supported; use one item per line")
    if s[:1] in ("&", "*", "!", "|", ">", "@", "`", "%"):
        _err(line, "anchors, aliases, tags and block scalars are not supported")
    m = re.search(r"\s#", s)                      # a comment after a plain value
    if m:
        s = s[:m.start()].rstrip()
    if s in _NULL:
        return None
    if s in _BOOL_FORMS:
        return _BOOL[s.lower()]
    if _INT.match(s):
        return int(s)
    if _OTHER.match(s):
        _err(line, "a plain value PyYAML would not read as text or a whole number; quote it")
    if s.startswith("- ") or s == "-" or s.startswith("? ") or re.search(r":(\s|$)", s):
        _err(line, "a plain value that YAML would split; quote it")
    return s


_KEY = re.compile(r"""^(?P<key>'(?:[^']|'')*'|"(?:[^"\\]|\\.)*"|[^\s'"#\-?:\[\]{},&*!|>@`%][^:#]*?)\s*:(?:\s+(?P<val>.*))?$""")


def _key(line, raw):
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        return _scalar(line, raw)
    v = _scalar(line, raw)
    return v


def _parse(lines, i, indent):
    first = lines[i]
    if first.indent != indent:
        _err(first, "unexpected indentation")
    if first.text == "-" or first.text.startswith("- "):
        return _parse_list(lines, i, indent)
    return _parse_map(lines, i, indent)


def _value_after(lines, i, indent, line):
    """The block that follows a `key:` or `-` with nothing after it."""
    if i < len(lines) and lines[i].indent > indent:
        return _parse(lines, i, lines[i].indent)
    if i < len(lines) and lines[i].indent == indent and (lines[i].text.startswith("- ") or lines[i].text == "-"):
        return _parse_list(lines, i, indent)
    return None, i


def _parse_map(lines, i, indent):
    out = {}
    while i < len(lines) and lines[i].indent == indent:
        line = lines[i]
        if line.text.startswith("- ") or line.text == "-":
            break
        m = _KEY.match(line.text)
        if not m:
            _err(line, "expected `key: value`")
        k = _key(line, m.group("key"))
        if k in out:
            _err(line, "duplicate key %r" % (k,))
        val = m.group("val")
        if val is not None and val.strip() and not val.strip().startswith("#"):
            out[k] = _scalar(line, val)
            i += 1
        else:
            out[k], i = _value_after(lines, i + 1, indent, line)
    if i < len(lines) and lines[i].indent > indent:
        _err(lines[i], "unexpected indentation")
    return out, i


def _parse_list(lines, i, indent):
    out = []
    while i < len(lines) and lines[i].indent == indent and (lines[i].text.startswith("- ") or lines[i].text == "-"):
        line = lines[i]
        rest = line.text[1:]
        body = rest.lstrip(" ")
        if not body or body.startswith("#"):
            v, i = _value_after(lines, i + 1, indent, line)
            out.append(v)
            continue
        item_indent = indent + 1 + (len(rest) - len(body))
        m = _KEY.match(body)
        if m and body[:1] not in ("'", '"') or (m and re.match(r"""^('(?:[^']|'')*'|"(?:[^"\\]|\\.)*")\s*:(\s|$)""", body)):
            # A mapping that starts on the dash line: re-read it as if the key sat on its own line.
            sub = [_Line(line.no, item_indent, body)] + lines[i + 1:]
            v, j = _parse_map(sub, 0, item_indent)
            out.append(v)
            i = i + j
            continue
        out.append(_scalar(line, body))
        i += 1
    return out, i


def loads(text):
    lines = _lines(text)
    if not lines:
        return None
    v, i = _parse(lines, 0, lines[0].indent)
    if i != len(lines):
        _err(lines[i], "unexpected line")
    return v
