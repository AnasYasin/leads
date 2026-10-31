"""Getro dates. 29 Oct 2026: `created_at` is epoch seconds, and storing the digits made every Getro
row undated for prescore.py, so the whole source sat at the end of the reading order for 12 weeks."""
import datetime

import collect_getro as C
import prescore


def test_epoch_seconds_become_an_iso_date():
    assert C.iso(1793275017) == "2026-10-29"
    assert C.iso("1793275017") == "2026-10-29"
    assert C.iso("2026-10-01T08:00:00Z") == "2026-10-01"
    assert C.iso(None) == "" and C.iso("") == "" and C.iso("abc") == "" and C.iso(0) == "1970-01-01"
    assert C.iso(10 ** 20) == ""


def test_a_fresh_getro_row_lands_in_the_first_reading_group(monkeypatch):
    now = int(datetime.datetime(2026, 10, 29, 9, tzinfo=datetime.timezone.utc).timestamp())
    payload = {"results": {"jobs": [
        {"title": "Machine Learning Engineer", "url": "https://x.example/1", "created_at": now - 3600,
         "organization": {"name": "X"}, "locations": ["Berlin, Germany"]},
        {"title": "Old role", "url": "https://x.example/2", "created_at": now - 200 * 86400,
         "organization": {"name": "X"}, "locations": [{"name": "Munich, Germany"}]}]}}
    monkeypatch.setattr(C, "page", lambda cid, p: payload if p == 0 else {"results": {"jobs": []}})
    name, jobs, err = C.one((1, "Test VC"))
    assert err is None and [j["date"] for j in jobs] == ["2026-10-29", "2026-04-12"]
    assert jobs[1]["location"] == "Munich, Germany"
    today = datetime.date(2026, 10, 29)
    assert prescore.fresh_group(jobs[0], today) == 0
    assert prescore.fresh_group(jobs[1], today) > prescore.fresh_group(jobs[0], today)
    # The old shape, bare digits, is what read as undated: the last group.
    assert prescore.fresh_group(dict(jobs[0], date=str(now)), today) == prescore.fresh_group(dict(jobs[0], date=""), today)
