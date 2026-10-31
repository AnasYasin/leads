import datetime
import json

import pytest

import sweep_due as W


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "PATH", str(tmp_path / "state/sweep.json"))
    return tmp_path


def say(capsys, argv):
    W.main(argv)
    return capsys.readouterr().out


def test_no_record_is_due(state, capsys):
    assert say(capsys, []).startswith("DUE")


def test_due_after_seven_days(state, capsys):
    old = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    json.dump({"last": old, "history": []}, open(W.PATH, "w"))
    assert say(capsys, []).startswith("DUE")
    recent = (datetime.date.today() - datetime.timedelta(days=6)).isoformat()
    json.dump({"last": recent, "history": []}, open(W.PATH, "w"))
    assert say(capsys, []).startswith("NOT DUE")


def test_done_records_and_bad_usage(state, capsys):
    say(capsys, ["--done", "2", "found two", "slug-a"])
    st = json.load(open(W.PATH))
    assert st["last"] == datetime.date.today().isoformat() and st["history"][-1]["added"] == ["slug-a"]
    with pytest.raises(SystemExit):
        W.main(["--done", "x", "bad"])


FEED = """<rss><channel>
<item><title><![CDATA[#DealMonitor - Nomos erhält 20 Millionen]]></title><link>https://x/1</link><pubDate>Mon, 28 Sep 2026 08:00:00 +0200</pubDate></item>
<item><title>#Interview - Wir wachsen</title><link>https://x/2</link><pubDate>Mon, 28 Sep 2026 07:00:00 +0200</pubDate></item>
<item><title>#StartupTicker - +++ Old +++</title><link>https://x/3</link><pubDate>Mon, 01 Sep 2026 07:00:00 +0200</pubDate></item>
</channel></rss>"""


class Resp:
    def __init__(self, b):
        self.b = b

    def read(self):
        return self.b.encode()


def test_leads_filters_funding_and_stops_at_cutoff(monkeypatch):
    calls = []
    monkeypatch.setattr(W.urllib.request, "urlopen", lambda req, timeout=0: calls.append(1) or Resp(FEED))
    rows = W.leads(datetime.date(2026, 9, 20))
    assert [r[1] for r in rows] == ["#DealMonitor - Nomos erhält 20 Millionen"]
    assert len(calls) == 1                       # the oldest item is before the cutoff, so no page 2


def test_leads_network_error_returns_empty(monkeypatch, capsys):
    def boom(*a, **k):
        raise OSError("down")
    monkeypatch.setattr(W.urllib.request, "urlopen", boom)
    assert W.leads(datetime.date(2026, 9, 20)) == []
    assert "FEED ERROR" in capsys.readouterr().err


def test_leads_skips_malformed_items(monkeypatch):
    bad = FEED.replace("<pubDate>Mon, 28 Sep 2026 07:00:00 +0200</pubDate>", "<pubDate>garbage</pubDate>", 1)
    bad = bad.replace("<rss><channel>", "<rss><channel><item><link>https://x/0</link></item>", 1)
    monkeypatch.setattr(W.urllib.request, "urlopen", lambda req, timeout=0: Resp(bad))
    rows = W.leads(datetime.date(2026, 9, 20))
    assert [r[1] for r in rows] == ["#DealMonitor - Nomos erhält 20 Millionen"]
