"""Tests for level maps, geometry, and campaign structure (levels.py)

Split out of the old test_app.py (Step C)."""

import firefighter_defense as g
from helpers import *  # shared test builders/play-drivers

# --- ITEM-007: the level map, path, and building -----------------------------

def test_at_least_two_levels_exist():
    assert g.level_count() >= 2


def test_levels_are_different_maps():
    a = g.level_json(0)
    b = g.level_json(1)
    assert a["path"] != b["path"] or a["building"] != b["building"]


def test_level_has_path_spots_building_and_lives():
    lv = g.level_json(0)
    assert len(lv["path"]) >= 2
    assert len(lv["build_spots"]) >= 1
    assert lv["building"]["lives"] >= 1


def test_bad_level_index_is_handled():
    assert g.get_level(999) is None
    assert g.level_json(999) is None


def test_path_point_at_start_and_end():
    wp = [[0, 0], [100, 0], [100, 100]]
    assert g.path_point_at(wp, 0) == (0.0, 0.0)
    assert g.path_point_at(wp, 1) == (100.0, 100.0)


def test_path_point_at_midpoint_is_on_the_path():
    # Total length 200; halfway (t=0.5) is at the corner (100, 0).
    wp = [[0, 0], [100, 0], [100, 100]]
    x, y = g.path_point_at(wp, 0.5)
    assert abs(x - 100.0) < 1e-6 and abs(y - 0.0) < 1e-6


def test_path_point_at_quarter():
    wp = [[0, 0], [100, 0], [100, 100]]
    x, y = g.path_point_at(wp, 0.25)   # 50 units along the first segment
    assert abs(x - 50.0) < 1e-6 and abs(y - 0.0) < 1e-6


# --- ITEM-008: waves, marching fires, lives, win/lose ------------------------

def test_schedule_matches_wave_fire_count():
    lv = g.get_level(0)
    sched = g.build_schedule(lv)
    total = sum(len(w["fires"]) for w in lv["waves"])
    assert len(sched) == total
    ts = [e["t"] for e in sched]
    assert ts == sorted(ts)  # spawns are time-ordered


def test_level_json_has_waves():
    assert len(g.level_json(0)["waves"]) >= 1


def test_level_json_has_budget_and_schedule():
    lv = g.level_json(0)
    assert lv["budget"] >= 1
    assert isinstance(lv["schedule"], list) and len(lv["schedule"]) >= 1


def test_every_build_spot_has_clearance():
    for i in range(g.level_count()):
        lv = g.get_level(i)
        for (x, y) in lv["build_spots"]:
            d = g.point_to_path_distance(x, y, lv["path"])
            assert d >= g.BUILD_SPOT_CLEARANCE, f"level {i} spot ({x},{y}) only {d:.0f}px from path"


def test_point_to_path_distance_basic():
    path = [[0, 0], [100, 0]]
    assert abs(g.point_to_path_distance(50, 30, path) - 30) < 1e-6
    assert abs(g.point_to_path_distance(50, 0, path) - 0) < 1e-6


def test_level0_has_the_three_taught_classes():
    seen = {ev["class"] for ev in g.build_schedule(g.LEVELS[0])}
    assert {"A", "electrical", "F"} <= seen


# --- ITEM-016: the combined level + the gas/power shut-off mechanic -----------

def test_combined_level_exists_and_declares_supplies():
    lv2 = next((l for l in g.LEVELS if l.get("supplies")), None)
    assert lv2 is not None, "expected a level that declares supply hazards"
    assert set(lv2["supplies"]) == {"gas", "power"}
    seen = {ev["class"] for ev in g.build_schedule(lv2)}
    assert {"B", "C", "D"} <= seen, "combined level should teach liquids, gases, metals"


def test_no_single_tool_spam_wins_any_level():
    for i in range(g.level_count()):
        lv = g.LEVELS[i]
        for t in g.TOOLS:
            assert _spam(lv, t["id"]) == "lost", \
                f"level {i} can be won by spamming {t['id']} — unsafe play must not win"


def test_levels_are_never_trivially_single_class():
    # Every level teaches at least two distinct fire classes. This is the property
    # that keeps "only safe play wins" true: a single correct tool can never trivially
    # clear a whole level, because at least two classes with different right tools
    # appear. (Superseded the old "distinct-class counts non-decreasing across the
    # LEVELS array" proxy, which assumed array order = difficulty order — no longer
    # true once the story campaign orders levels by narrative and the Schlosserei
    # training level, richest in classes, sits outside the campaign — ITEM-027.)
    for i in range(g.level_count()):
        seen = {ev["class"] for ev in g.build_schedule(g.LEVELS[i])}
        assert len(seen) >= 2, f"level {i} ('{g.LEVELS[i]['name']}') teaches only {seen}"


def test_campaign_is_in_order_and_stays_gentle():
    # The four story missions play in order 1..4, and each stays within a small,
    # learnable band of distinct fire classes (2..4) — the campaign opens and stays
    # gentle even though it's ordered by story, not by raw mechanical complexity.
    missions = g.campaign_missions()
    assert [m["mission"] for m in missions] == [1, 2, 3, 4]
    for m in missions:
        seen = {ev["class"] for ev in g.build_schedule(g.LEVELS[m["index"]])}
        assert 2 <= len(seen) <= 4, f"mission {m['mission']} teaches {seen}"


# --- ITEM-026 / ITEM-027: Anton as narrator + the four story missions ---------

def test_campaign_has_four_story_missions_in_order():
    missions = g.campaign_missions()
    assert [m["mission"] for m in missions] == [1, 2, 3, 4]
    assert [m["key"] for m in missions] == ["fachwerk", "bibliothek", "kurpark", "feuerwerk"]


def test_training_level_is_outside_the_campaign():
    # The Schlosserei workshop stays available as a side/training level, not a mission.
    schlosserei = g.level_by_key("schlosserei")
    assert schlosserei is not None
    assert not schlosserei.get("campaign")
    assert schlosserei.get("mission") is None


def test_library_mission_is_electrical_among_burning_books():
    # DECISION (Adam, review): the library is an ELECTRICAL fire (water dangerous)
    # among ordinary burning books/paper (Class A) — no burning-metal fire here.
    # The power supply can be cut (the clean, no-water fix that protects the records),
    # which is also what keeps the "no single tool wins" guard green.
    lv = g.level_by_key("bibliothek")
    seen = {ev["class"] for ev in g.build_schedule(lv)}
    assert seen == {"electrical", "A"}
    assert "power" in lv.get("supplies", [])      # you must cut the power first
    assert g.MATRIX["electrical"]["water"] == "danger"


def test_firework_mission_teaches_liquids_electrical_and_the_moved_metal_fire():
    # The brief's classes (B + electrical) plus the relocated burning-metal fire (D).
    lv = g.level_by_key("feuerwerk")
    seen = {ev["class"] for ev in g.build_schedule(lv)}
    assert {"B", "electrical", "D"} <= seen
    assert seen <= {c["id"] for c in g.FIRE_CLASSES}  # no invented "firework" class


def test_burning_metal_fire_is_not_in_the_library():
    # The Class D (burning-metal) fire moved OUT of the library into the finale.
    lib = {ev["class"] for ev in g.build_schedule(g.level_by_key("bibliothek"))}
    assert "D" not in lib


def test_every_campaign_mission_has_antons_framing():
    for m in g.campaign_missions():
        lines = g.mission_lines_de(m["key"])
        for field in ("open", "anecdote", "hint", "close"):
            assert lines.get(field, "").strip(), f"{m['key']} missing Anton's {field}"


# --- ITEM-028: Anton's arc, reward vignettes, library name beat, and finale ----

def test_anton_arc_has_a_courage_line_for_every_stage():
    # A mood line for 0..N missions completed (N = number of story missions).
    arc = g.anton_arc_de()
    assert len(arc) == len(g.campaign_missions()) + 1
    assert all(line.strip() for line in arc)


def test_every_campaign_mission_has_a_reward_vignette():
    for m in g.campaign_missions():
        v = g.vignette_de(m["key"])
        assert v.get("scene", "").strip(), f"{m['key']} vignette has no scene"
        assert v.get("title", "").strip() and v.get("caption", "").strip()
    # ...and it rides along in the level payload the browser fetches.
    lib = g.level_by_key("bibliothek")
    idx = next(i for i, lv in enumerate(g.LEVELS) if lv is lib)
    assert g.level_json(idx)["vignette"]["scene"] == "records"


def test_charge_tightens_across_the_four_campaign_missions():
    charges = [g.tower_charge_for(m) for m in ({"mission": 1}, {"mission": 2}, {"mission": 3}, {"mission": 4})]
    assert charges[0] > charges[1] > charges[2] > charges[3], charges
    assert charges[0] == g.TOWER_CHARGE_BASE
    assert all(c >= g.MIN_TOWER_CHARGE for c in charges)


def test_non_campaign_levels_use_the_generous_baseline_charge():
    non_campaign = next(lv for lv in g.LEVELS if not lv.get("campaign"))
    assert g.tower_charge_for(non_campaign) == g.TOWER_CHARGE_BASE == g.tower_charge_for({"mission": 1})
