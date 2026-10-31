#!/usr/bin/env python3
"""One HTML-to-text cleaner for every collector and reader.

Added 2 Oct 2026 (docs/PROBLEMS.md, group 1). Before this, seven scripts each carried their own
`strip()`, and they disagreed:

  - collect_ats.py removed tags first and decoded entities second. Greenhouse sends its HTML
    entity-escaped, so nothing was removed and all 3,029 Greenhouse rows kept their markup.
  - collect_ats.py, collect_arbeitnow.py and read_jobs.py flattened everything to one line. A list
    under a heading lost its shape: BaehrBots lists "Deutschkenntnisse" as the last item under
    "Ein Plus", and flattened it read "Sehr gute Englischkenntnisse und Deutschkenntnisse".
  - every one of them replaced an inline tag with a space, so "<b>Crisp</b>," became "Crisp ,".

`html_to_text` keeps the structure a reader needs and nothing else:

  - one block (paragraph, list item, heading, table row) per line
  - a list item starts with "• "
  - a heading has an empty line before it
  - no tags, no entities, no script or style content, no invisible characters

Nothing is cut. The text is as long as the posting.

    python3 scripts/textclean.py < posting.html
"""
import html
import re
import sys
from html.parser import HTMLParser

# Content that is never part of the posting.
SKIP = {"script", "style", "noscript", "template", "svg", "head", "title", "iframe", "select", "button"}
# A new line before and after.
BLOCK = {"p", "div", "section", "article", "header", "footer", "main", "aside", "nav", "ul", "ol", "dl",
         "dt", "dd", "table", "thead", "tbody", "tfoot", "tr", "blockquote", "pre", "figure", "figcaption",
         "form", "fieldset", "address", "details", "summary", "hr", "br"}
HEADING = {"h1", "h2", "h3", "h4", "h5", "h6"}
CELL = {"td", "th"}
VOID = {"br", "hr", "img", "input", "meta", "link", "wbr", "area", "base", "col", "embed", "source", "track"}

BULLET = "• "
# Zero-width and formatting characters that render as nothing: soft hyphen, zero-width space and
# joiners, the bidi marks, word joiner, BOM.
INVISIBLE = re.compile("[­​-‏‪-‮⁠-⁤﻿]")
# Every space-like character except the line break.
SPACES = re.compile("[ \t\r\f\v   -   　]+")
CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Element names that mark a string as HTML. "vector<int>" and "a <b" in a plain text are not tags.
_NAMES = (r"(?:p|div|span|br|ul|ol|li|strong|b|i|em|u|a|h[1-6]|table|thead|tbody|tfoot|tr|td|th|caption|col|colgroup|"
          r"section|article|header|footer|main|nav|aside|img|hr|blockquote|pre|code|font|small|big|sup|sub|label|"
          r"figure|figcaption|style|script|noscript|template|html|body|head|title|meta|link|dl|dt|dd|center|s|strike|"
          r"mark|del|ins|abbr|cite|time|address|details|summary|form|input|button|select|option|svg|path|iframe|"
          r"video|picture|source|wbr|o:p)")
TAG = re.compile(r"</?%s(?:\s[^<>]*)?/?>|<!--|<!\[CDATA\[" % _NAMES, re.I)
ESCAPED_TAG = re.compile(r"&lt;/?%s(?:\s[^&]*?)?/?&gt;" % _NAMES, re.I)
ENTITY = re.compile(r"&(?:[a-zA-Z][a-zA-Z0-9]{1,30}|#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6});")
CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)
# A bullet character typed into the text, at the start of a line.
TYPED_BULLET = re.compile("^[•·●▪◦‣⁃∙▫■➢✔✓→►▶♦]\\s*")


# Only these two need their end tag to be parsed at all. The rest of SKIP is dropped when a
# fragment opens one and never closes it, so an unclosed <button> cannot swallow the posting.
SKIP_MIN = {"script", "style"}


class _Text(HTMLParser):
    def __init__(self, skip_tags=SKIP):
        super().__init__(convert_charrefs=True)
        self.skip_tags = skip_tags
        self.out = []
        self.skip = 0          # depth inside a SKIP element
        self.breaks = 0        # line breaks owed before the next text
        self.bullet = False    # a list item opened and has no text yet
        self.started = False

    def _break(self, n):
        if self.breaks < n:
            self.breaks = n

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            if tag not in VOID:
                self.skip += 1
            return
        if self.skip:
            return
        if tag == "li":
            self._break(1)
            self.bullet = True
        elif tag in HEADING:
            self._break(2)
        elif tag in BLOCK:
            self._break(1)
        elif tag in CELL:
            self.out.append(" ")

    def handle_startendtag(self, tag, attrs):
        if not self.skip and (tag in BLOCK or tag == "li"):
            self._break(1)

    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            if self.skip:
                self.skip -= 1
            return
        if self.skip:
            return
        if tag == "li":
            self.bullet = False
            self._break(1)
        elif tag in HEADING or tag in BLOCK:
            self._break(1)
        elif tag in CELL:
            self.out.append(" ")

    def handle_data(self, data):
        if self.skip:
            return
        if not data.strip():
            # White space between two inline elements is one space. Between blocks it is nothing,
            # and the line clean-up below removes it.
            if data:
                self.out.append(" ")
            return
        if self.breaks and self.started:
            self.out.append("\n" * self.breaks)
        self.breaks = 0
        self.started = True
        if self.bullet:
            self.out.append(BULLET)
            self.bullet = False
        # A line break inside a text node is white space in HTML, never a new line.
        self.out.append(re.sub(r"\s+", " ", data))

    def text(self):
        return "".join(self.out)


def _lines(t):
    """Trim every line, drop the invisible characters, allow one empty line at most."""
    t = INVISIBLE.sub("", t)
    t = CONTROL.sub(" ", t.replace("\r\n", "\n").replace("\r", "\n"))
    out, blank = [], 0
    for line in t.split("\n"):
        line = SPACES.sub(" ", line).strip()
        m = TYPED_BULLET.match(line)
        if m:
            line = (BULLET + line[m.end():]).strip() if line[m.end():].strip() else ""
        if not line:
            blank += 1
            continue
        if out and blank:
            out.append("")
        blank = 0
        out.append(line)
    return "\n".join(out)


def has_tags(s):
    return bool(TAG.search(s or ""))


def html_to_text(s):
    """Clean text from HTML, entity-escaped HTML or plain text. Never raises, never cuts."""
    if not s:
        return ""
    if not isinstance(s, str):
        s = str(s)
    try:
        s = CDATA.sub(lambda m: m.group(1), s)
        # Greenhouse and a few feeds send the HTML escaped: "&lt;p&gt;You will ...". Decode once, so
        # the tags are tags. Text that only mentions "&lt;" is left for the parser to decode.
        if ESCAPED_TAG.search(s) and len(ESCAPED_TAG.findall(s)) >= len(TAG.findall(s)):
            s = html.unescape(s)
        if not has_tags(s):
            # Plain text. The line breaks are the author's own structure, so they stay.
            return _lines(html.unescape(s))
        p = _Text()
        p.feed(s)
        p.close()
        if p.skip:
            p = _Text(SKIP_MIN)
            p.feed(s)
            p.close()
        t = p.text()
        # An entity escaped two or three times ("&amp;amp;", "&amp;amp;nbsp;") survives one decode.
        for _ in range(3):
            if not ENTITY.search(t):
                break
            t = html.unescape(t)
        return _lines(t)
    except Exception:
        # A parser failure must not lose the posting. Fall back to the plain regex strip.
        t = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
        t = re.sub(r"<(?:br|/p|/li|/div|/h[1-6]|/tr)\b[^>]*>", "\n", t, flags=re.I)
        return _lines(html.unescape(re.sub(r"<[^>]+>", " ", t)))


def as_html(s):
    """A text field as an HTML fragment. Plain text keeps its line breaks, HTML is passed through."""
    s = CDATA.sub(lambda m: m.group(1), s or "")
    if ESCAPED_TAG.search(s) and len(ESCAPED_TAG.findall(s)) >= len(TAG.findall(s)):
        s = html.unescape(s)
    if has_tags(s):
        return s
    return html.escape(html.unescape(s), quote=False).replace("\r\n", "\n").replace("\n", "<br>")


def join_html(*parts):
    """One HTML document from a posting's text fields, in order. A part is a string or a
    (heading, string) pair. Empty parts are left out. Boards split a posting over several fields
    (Lever: description, lists, additional; Personio: one jobDescription per section), and the
    requirements usually sit in a later one."""
    out = []
    for part in parts:
        head, text = part if isinstance(part, tuple) else ("", part)
        if not text or not str(text).strip():
            continue
        if head and str(head).strip():
            out.append("<h3>%s</h3>" % html.escape(html.unescape(str(head).strip()), quote=False))
        out.append("<div>%s</div>" % as_html(str(text)))
    return "\n".join(out)


def leftovers(t):
    """What a clean text must not contain, as {problem: count}. Empty when the text is clean.
    Used by the tests and by the per-run report, so a cleaning regression shows up as a number."""
    t = t or ""
    found = {
        "tags": len(TAG.findall(t)),
        "escaped_tags": len(ESCAPED_TAG.findall(t)),
        "entities": len(ENTITY.findall(t)),
        "cdata": t.count("]]>") + t.count("<![CDATA["),
        "invisible": len(INVISIBLE.findall(t)),
        "control": len(CONTROL.findall(t)),
        "double_space": len(re.findall(r"[ \t ]{2,}", t)),
        "blank_runs": len(re.findall(r"\n{3,}", t)),
        "space_at_line_edge": len(re.findall(r"(?m)^[ \t]+\S|\S[ \t]+$", t)),
    }
    return {k: v for k, v in found.items() if v}


if __name__ == "__main__":
    print(html_to_text(sys.stdin.read()))
