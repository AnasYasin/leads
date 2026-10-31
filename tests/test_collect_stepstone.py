import collect_stepstone as C


def test_fetch_quotes_invisible_characters(monkeypatch):
    seen = []

    class R:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"ok"

    def fake(req, timeout):
        seen.append(req.full_url)
        return R()

    monkeypatch.setattr(C.urllib.request, "urlopen", fake)
    url = "https://www.stepstone.de/stellenangebote--Arbeit‍-Wuerth--14418986-inline.html?x=1&y=2"
    assert C.fetch(url) == (200, "ok")
    assert seen == ["https://www.stepstone.de/stellenangebote--Arbeit%E2%80%8D-Wuerth--14418986-inline.html?x=1&y=2"]
    assert C.MAX_JOB_FETCH >= 1000
