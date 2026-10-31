import slots


def test_slot_boundaries():
    # 10:00 Berlin run starts 08:00 UTC, the 13:30 leftover run 11:30 UTC, the 19:00 run 17:00 UTC
    assert slots.slot_for(8) == "morning" and slots.slot_for(9) == "morning"
    assert slots.slot_for(10) == "noon" and slots.slot_for(11) == "noon" and slots.slot_for(14) == "noon"
    assert slots.slot_for(15) == "evening" and slots.slot_for(17) == "evening" and slots.slot_for(23) == "evening"
    assert slots.slot_for(0) == "morning"


def test_build_latest_orders_three_slots(tmp_path, monkeypatch):
    import build_latest as B
    names = ["2026-09-29-evening.md", "2026-09-29-morning.md", "2026-09-29-noon.md", "2026-09-28-evening.md"]
    ordered = sorted((tmp_path / n for n in names), key=B.sort_key)
    assert [p.name for p in ordered] == ["2026-09-28-evening.md", "2026-09-29-morning.md",
                                         "2026-09-29-noon.md", "2026-09-29-evening.md"]
