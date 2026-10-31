"""archive_run.py: the run's working files go to a GitHub Release, the raw rows stay out, old
releases are deleted, and nothing here can fail the run. Added 31 Oct 2026."""
import datetime
import io
import json
import os
import zipfile

import archive_run as A


def scratch(tmp_path):
    (tmp_path / "ats.json").write_text(json.dumps([dict(company="Acme", title="ML Engineer", location="Berlin", date="2026-10-31",
                                                         url="https://acme.example/1", desc="x" * 5000, extra="dropped")]))
    (tmp_path / "linkedin.json").write_text(json.dumps([dict(company="Beta", title="CV Engineer", url="https://li.example/2")]))
    (tmp_path / "xing.json").write_text("not json")
    (tmp_path / "linkedin_read.json").write_text("{}")
    (tmp_path / "ats.json.report").write_text("209 boards")
    (tmp_path / "ats.log").write_text("ok")
    (tmp_path / "candidates.json").write_text("[]")
    (tmp_path / "batches").mkdir()
    (tmp_path / "batches" / "batch_1.txt").write_text("job text")
    (tmp_path / "run_slot.json").write_text(json.dumps(dict(date="2026-10-31", slot="morning", started="2026-10-31T08:00:00+00:00")))
    (tmp_path / "shortlist.json").write_text(json.dumps(dict(jobs=[{}, {}], coverage=dict(candidates=300, read_full=55))))
    return str(tmp_path)


class Fake:
    """urlopen stand-in that records every call and answers like GitHub."""
    def __init__(self, releases=()):
        self.calls, self.releases = [], list(releases)

    def __call__(self, req, timeout=0):
        self.calls.append((req.get_method(), req.full_url, req.data, req.get_header("Content-type")))
        if req.get_method() == "POST" and "/assets" in req.full_url and getattr(self, "upload_hangs", False):
            raise TimeoutError("The read operation timed out")
        if req.get_method() == "GET" and "/releases/tags/" in req.full_url:
            if getattr(self, "tag_exists", False):
                body = {"id": 7, "upload_url": "https://uploads.github.com/repos/x/y/releases/7/assets{?name,label}"}
                return io.BytesIO(json.dumps(body).encode())
            raise A.urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(b"{}"))
        if req.get_method() == "GET" and req.full_url.endswith("/releases/7"):
            body = {"id": 7, "assets": [{"name": "run-2026-10-31-morning.zip"}] if getattr(self, "asset_landed", False) else []}
        elif req.get_method() == "POST" and req.full_url.endswith("/releases"):
            body = {"id": 7, "upload_url": "https://uploads.github.com/repos/x/y/releases/7/assets{?name,label}"}
        elif req.get_method() == "GET":
            body = self.releases
        else:
            body = {}
        return io.BytesIO(json.dumps(body).encode())


def test_the_zip_holds_the_working_files_and_compact_cards_and_not_the_raw_rows(tmp_path):
    data = A.bundle(scratch(tmp_path))
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    assert {"cards.json", "candidates.json", "batches/batch_1.txt", "ats.log", "ats.json.report", "run_slot.json"} <= names
    assert not {"ats.json", "linkedin.json", "xing.json", "linkedin_read.json"} & names
    cards = json.loads(z.read("cards.json"))
    assert cards == [dict(source="ats", company="Acme", title="ML Engineer", location="Berlin", date="2026-10-31", url="https://acme.example/1"),
                     dict(source="linkedin", company="Beta", title="CV Engineer", location="", date="", url="https://li.example/2")]


def test_upload_creates_the_release_attaches_the_zip_and_prunes_old_runs(tmp_path, monkeypatch):
    old = dict(id=1, tag_name="run-2026-07-01-morning", created_at="2026-07-01T08:30:00Z")
    young = dict(id=2, tag_name="run-2026-10-30-evening", created_at="2026-10-30T17:30:00Z")
    other = dict(id=3, tag_name="v1.0", created_at="2026-01-01T00:00:00Z")
    fake = Fake([old, young, other])
    monkeypatch.setattr(A.urllib.request, "urlopen", fake)
    sc = scratch(tmp_path)
    line = A.upload(sc, "tok", today=datetime.date(2026, 10, 31))
    assert line.startswith("archive: run-2026-10-31-morning, ") and line.endswith("1 old release deleted")
    methods = [(m, u.split("github.com", 1)[1]) for m, u, _, _ in fake.calls]
    assert methods[0] == ("GET", "/repos/AnasYasin/job_radar/releases/tags/run-2026-10-31-morning")  # 404: not there yet
    assert methods[1] == ("POST", "/repos/AnasYasin/job_radar/releases")
    assert json.loads(fake.calls[1][2])["body"] == "2026-10-31 morning: 300 candidates, 55 read in full, 2 sent"
    assert methods[2] == ("POST", "/repos/x/y/releases/7/assets?name=run-2026-10-31-morning.zip") and fake.calls[2][3] == "application/zip"
    assert zipfile.ZipFile(io.BytesIO(fake.calls[2][2])).namelist()  # the attached bytes are the zip
    assert methods[3] == ("GET", "/repos/AnasYasin/job_radar/releases?per_page=100")
    assert methods[4:] == [("DELETE", "/repos/AnasYasin/job_radar/releases/1"),
                           ("DELETE", "/repos/AnasYasin/job_radar/git/refs/tags/run-2026-07-01-morning")]
    # a rerun after a lost reply finds the release already there and only attaches the zip
    fake = Fake([])
    fake.tag_exists = True
    monkeypatch.setattr(A.urllib.request, "urlopen", fake)
    A.upload(sc, "tok", today=datetime.date(2026, 10, 31))
    assert [m for m, u, _, _ in fake.calls] == ["GET", "POST", "GET"] and "/assets" in fake.calls[1][1]


def test_no_token_or_an_api_error_never_fails_the_run(tmp_path, monkeypatch, capsys):
    sc = scratch(tmp_path)
    monkeypatch.delenv("RADAR_GITHUB_TOKEN", raising=False)
    assert A.main(sc) == 0 and "archive: skipped" in capsys.readouterr().out
    monkeypatch.setenv("RADAR_GITHUB_TOKEN", "tok")

    def boom(req, timeout=0):
        raise OSError("connection refused")
    monkeypatch.setattr(A.urllib.request, "urlopen", boom)
    assert A.main(sc) == 0 and "archive: failed, connection refused" in capsys.readouterr().out


def test_an_upload_whose_reply_times_out_is_checked_by_looking_for_the_asset(tmp_path, monkeypatch):
    sc = scratch(tmp_path)
    fake = Fake([])
    fake.upload_hangs, fake.asset_landed = True, True
    monkeypatch.setattr(A.urllib.request, "urlopen", fake)
    assert A.upload(sc, "tok", today=datetime.date(2026, 10, 31)).startswith("archive: run-2026-10-31-morning, ")
    assert [m for m, u, _, _ in fake.calls] == ["GET", "POST", "POST", "GET", "GET"]  # tag lookup, create, upload, check the asset, prune
    fake = Fake([])
    fake.upload_hangs, fake.asset_landed = True, False
    monkeypatch.setattr(A.urllib.request, "urlopen", fake)
    try:
        A.upload(sc, "tok", today=datetime.date(2026, 10, 31))
        assert False, "an upload with no asset must fail"
    except TimeoutError:
        pass

