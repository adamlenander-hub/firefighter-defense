"""
Checks for the ITEM-005 foundation.

These exercise the parts that don't need the web framework running: the database
builds itself, survives being called twice, is rebuilt after deletion, honours a
custom location, and the page/health content comes out right and in German.

If FastAPI isn't installed in this environment, a tiny stand-in is injected so the
module can still be imported and its logic tested. The FastAPI web layer itself is
confirmed separately by actually running the app where the dependencies are present
(the user's machine or the host).
"""

import importlib
import os
import sys
import types


def _ensure_importable():
    """Let the module import even if FastAPI isn't installed here, by injecting a
    minimal stand-in. Uses the real FastAPI when it's available."""
    try:
        import fastapi  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    fake = types.ModuleType("fastapi")

    class _App:
        def __init__(self, *a, **k):
            pass

        def _decorator(self, *a, **k):
            def wrap(fn):
                return fn
            return wrap

        get = _decorator
        post = _decorator
        on_event = _decorator

    def _response(content=None, *a, **k):
        return content

    fake.FastAPI = _App
    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = _response
    responses.JSONResponse = _response
    fake.responses = responses
    sys.modules["fastapi"] = fake
    sys.modules["fastapi.responses"] = responses


_ensure_importable()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
g = importlib.import_module("firefighter_defense")


def test_db_is_created(tmp_path):
    db = str(tmp_path / "test.db")
    assert not os.path.exists(db)
    g.init_db(db)
    assert os.path.exists(db), "the database file should exist after init"


def test_schema_version_recorded(tmp_path):
    db = str(tmp_path / "test.db")
    g.init_db(db)
    assert g.read_meta("schema_version", db) == str(g.SCHEMA_VERSION)


def test_init_is_idempotent(tmp_path):
    db = str(tmp_path / "test.db")
    g.init_db(db)
    g.init_db(db)  # calling again must not error or duplicate
    assert g.read_meta("schema_version", db) == str(g.SCHEMA_VERSION)


def test_db_rebuilds_after_deletion(tmp_path):
    db = str(tmp_path / "test.db")
    g.init_db(db)
    os.remove(db)
    assert not os.path.exists(db)
    g.init_db(db)
    assert os.path.exists(db), "deleting the database and restarting should recreate it"


def test_custom_database_path_is_used(tmp_path):
    nested = str(tmp_path / "sub" / "dir" / "game.db")
    g.init_db(nested)  # a fresh, non-existent folder should be created
    assert os.path.exists(nested)


def test_game_page_is_german_and_has_canvas():
    html = g.render_game_html()
    assert "<html lang=\"de\">" in html
    assert "Königstein" in html
    assert "<canvas" in html


def test_health_payload_shape():
    g.init_db()  # ensure the default db exists so schema_version reads back
    payload = g.health_payload()
    assert payload["status"] == "ok"
    assert payload["database"].endswith(".db")


# --- ITEM-006: the fire content and its guard check --------------------------

def test_content_loads(tmp_path):
    db = str(tmp_path / "c.db")
    g.init_db(db)
    nc, nt = g.content_counts(db)
    assert nc == len(g.FIRE_CLASSES)
    assert nt == len(g.TOOLS)


def test_matrix_is_complete(tmp_path):
    db = str(tmp_path / "c.db")
    g.init_db(db)
    m = g.load_matrix(db)
    assert len(m) == len(g.FIRE_CLASSES) * len(g.TOOLS)


def test_content_check_passes_on_good_data(tmp_path):
    db = str(tmp_path / "c.db")
    ok, problems = g.check_content(db)
    assert ok, f"expected a clean check, got: {problems}"


def test_key_facts_match_reference(tmp_path):
    db = str(tmp_path / "c.db")
    g.init_db(db)
    m = g.load_matrix(db)
    assert m[("electrical", "water")] == "danger"   # never water on electrical
    assert m[("F", "water")] == "danger"            # never water on cooking oil
    assert m[("F", "wetchem")] == "good"            # the kitchen extinguisher
    assert m[("electrical", "co2")] == "good"
    assert m[("D", "metal")] == "good"


def test_check_fails_when_a_safety_fact_is_wrong(tmp_path, monkeypatch):
    # Flip a safety-critical square to a dangerous mistake and confirm the check
    # catches it with a clear message (rather than silently teaching it).
    broken = {cid: dict(row) for cid, row in g.MATRIX.items()}
    broken["electrical"]["water"] = "good"
    monkeypatch.setattr(g, "MATRIX", broken)
    db = str(tmp_path / "broken.db")
    ok, problems = g.check_content(db)
    assert not ok
    assert any("SAFETY FACT WRONG" in p and "electrical" in p for p in problems)


def test_every_class_has_a_correct_tool(tmp_path):
    db = str(tmp_path / "c.db")
    g.init_db(db)
    m = g.load_matrix(db)
    for c in g.FIRE_CLASSES:
        assert any(m[(c["id"], t["id"])] == "good" for t in g.TOOLS), \
            f"{c['id']} has no correct tool"


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


def test_classes_display_distinct_icons_and_fields():
    disp = g.classes_display()
    icons = [c["icon"] for c in disp]
    assert len(set(icons)) == len(icons)  # each class tellable apart by icon alone
    assert all("colour" in c and "letter" in c for c in disp)


def test_one_fire_costs_one_life():
    gs = g.GameState(g.get_level(0))
    gs.lives = 3
    gs.spawned = len(gs.schedule)          # pretend everything already spawned
    gs.fires = [{"id": 99, "class": "A", "progress": 0.999}]
    gs.advance(1.0)                        # the fire reaches the building
    assert gs.lives == 2


def test_game_is_lost_when_fires_reach_building():
    gs = g.GameState(g.get_level(0))       # never extinguish anything
    for _ in range(100000):
        gs.advance(0.1)
        if gs.status != "playing":
            break
    assert gs.status == "lost"
    assert gs.lives == 0


def test_game_is_won_when_every_wave_is_cleared():
    lv = g.get_level(0)
    gs = g.GameState(lv)
    for _ in range(100000):
        gs.advance(0.1)
        for f in list(gs.fires):           # extinguish each fire as it appears
            gs.extinguish(f["id"])
        if gs.status != "playing":
            break
    assert gs.status == "won"
    assert gs.lives == lv["building"]["lives"]   # no life lost when all are stopped


# --- ITEM-009: towers, budget, auto-target, earn-back ------------------------

def _mini_level(**kw):
    lv = {"name": "t", "place_de": "t", "size": {"w": 400, "h": 100},
          "path": [[0, 0], [400, 0]], "build_spots": [[100, 0], [300, 0]],
          "building": {"x": 400, "y": 0, "lives": 3, "name_de": "X"},
          "budget": 100, "waves": []}
    lv.update(kw)
    return lv


def test_level_json_has_budget_and_schedule():
    lv = g.level_json(0)
    assert lv["budget"] >= 1
    assert isinstance(lv["schedule"], list) and len(lv["schedule"]) >= 1


def test_tools_have_costs():
    disp = g.tools_display()
    assert all(t["cost"] > 0 for t in disp)
    assert g.tool_cost("water") > 0 and g.tool_cost("nope") == 0


def test_place_tower_deducts_budget():
    gs = g.GameState(_mini_level(budget=100))
    ok, why = gs.place_tower(0, "water")
    assert ok, why
    assert gs.budget == 100 - g.tool_cost("water")
    assert len(gs.towers) == 1


def test_cannot_place_when_unaffordable():
    gs = g.GameState(_mini_level(budget=10))
    ok, why = gs.place_tower(0, "water")
    assert not ok and gs.budget == 10 and gs.towers == []


def test_cannot_place_twice_on_same_spot():
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, "water")
    ok, why = gs.place_tower(0, "foam")
    assert not ok


def test_bad_spot_index_refused():
    gs = g.GameState(_mini_level(budget=1000))
    ok, why = gs.place_tower(9, "water")
    assert not ok


def test_tower_extinguishes_in_range_and_earns_budget():
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, "water")                 # tower at (100,0)
    gs.fires = [{"id": 1, "class": "A", "progress": 0.25}]  # (100,0), in range
    b0 = gs.budget
    gs.advance(0.05)
    assert all(f["id"] != 1 for f in gs.fires)   # extinguished
    # Water is the ideal ("good") tool for Class A, so it earns the base reward plus
    # the smart-play bonus.
    assert gs.budget == b0 + g.EXTINGUISH_REWARD + g.SMART_BONUS  # earned back


def test_tower_out_of_range_misses():
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, "water")                 # tower at (100,0)
    gs.fires = [{"id": 2, "class": "A", "progress": 0.95}]  # (380,0), far away
    b0 = gs.budget
    gs.advance(0.05)
    assert any(f["id"] == 2 for f in gs.fires)   # not hit
    assert gs.budget == b0


def test_correct_tool_clears_a_wave_and_wins():
    lv = _mini_level(budget=1000, waves=[{"gap": 0.6, "fires": ["A", "A", "A"]}])
    gs = g.GameState(lv)
    gs.place_tower(0, "water")
    gs.place_tower(1, "water")           # water is correct for Class A
    for _ in range(100000):
        gs.advance(0.1)
        if gs.status != "playing":
            break
    assert gs.status == "won"


def test_wrong_tool_cannot_win():
    # More fires than the building has lives, so leaking them all = a loss.
    lv = _mini_level(budget=1000,
                     building={"x": 400, "y": 0, "lives": 3, "name_de": "X"},
                     waves=[{"gap": 0.5, "fires": ["electrical"] * 5}])
    gs = g.GameState(lv)
    gs.place_tower(0, "water")
    gs.place_tower(1, "water")           # water on electrical is dangerous — never puts it out
    for _ in range(100000):
        gs.advance(0.1)
        if gs.status != "playing":
            break
    assert gs.status == "lost"


# --- ITEM-010: the teaching mechanic (right / useless / dangerous) -----------

def _shot(tool, cls):
    """Fire one tower shot of `tool` at a fire of class `cls` sitting on the tower,
    and report (extinguished?, budget earned, game state)."""
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, tool)                       # tower at (100,0)
    gs.fires = [{"id": 1, "class": cls, "progress": 0.25}]   # (100,0), in range
    b0 = gs.budget
    gs.advance(0.02)                             # tower fires; movement negligible
    extinguished = all(f["id"] != 1 for f in gs.fires)
    return gs, extinguished, gs.budget - b0


def test_resolution_matches_the_matrix_for_every_pair():
    for cls, row in g.MATRIX.items():
        for tool, expected in row.items():
            gs, extinguished, earned = _shot(tool, cls)
            if expected in ("good", "weak"):
                assert extinguished, f"{tool} on {cls} ({expected}) should put it out"
                assert earned == g.EXTINGUISH_REWARD + (g.SMART_BONUS if expected == "good" else 0)
            elif expected == "danger":
                assert not extinguished, f"{tool} on {cls} is dangerous — must NOT put it out"
                assert earned == 0
                assert gs.stats["danger_hits"] == 1
            else:  # useless
                assert not extinguished, f"{tool} on {cls} is useless — must NOT put it out"
                assert earned == 0
                assert gs.stats["useless_hits"] == 1


def test_headline_lessons():
    # CO2 on electrical works; water on electrical is dangerous and never works.
    _, ext_co2, _ = _shot("co2", "electrical")
    _, ext_water_e, _ = _shot("water", "electrical")
    assert ext_co2 and not ext_water_e
    # Water clears ordinary solids; wet chemical clears cooking oil; water on oil backfires.
    _, ext_water_a, _ = _shot("water", "A")
    _, ext_wet_f, _ = _shot("wetchem", "F")
    gs_wf, ext_water_f, _ = _shot("water", "F")
    assert ext_water_a and ext_wet_f and not ext_water_f
    assert gs_wf.stats["danger_hits"] == 1


def test_ten_water_on_electrical_puts_out_zero():
    out = 0
    dangers = 0
    for _ in range(10):
        gs, ext, _ = _shot("water", "electrical")
        out += 1 if ext else 0
        dangers += gs.stats["danger_hits"]
    assert out == 0 and dangers == 10


def test_dangerous_shot_pushes_fire_toward_building():
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, "water")
    gs.fires = [{"id": 1, "class": "electrical", "progress": 0.25}]
    gs.advance(0.02)
    assert gs.fires and gs.fires[0]["progress"] > 0.25   # it lurched forward


# --- ITEM-011 / ITEM-012: meet-the-fire cards + wrong-tool feedback ----------

def test_every_class_has_a_card():
    for c in g.FIRE_CLASSES:
        assert g.CLASS_CARDS.get(c["id"], "").strip(), f"{c['id']} has no meet-the-fire card"


def test_classes_display_includes_card_and_right_tool():
    for d in g.classes_display():
        assert d["card_de"].strip()
        assert d["right_tool_de"].strip()


def test_feedback_none_for_correct_tools():
    assert g.feedback_reason("A", "water") is None      # good
    assert g.feedback_reason("A", "co2") is None         # weak (still fine) -> no scolding
    # (co2 on A is 'weak' -> acceptable -> no feedback message)


def test_feedback_danger_explains_and_suggests():
    msg = g.feedback_reason("electrical", "water")
    assert msg and "Strom" in msg                       # the danger reason
    assert g.right_tool_de("electrical") in msg          # suggests a correct tool
    fmsg = g.feedback_reason("F", "water")
    assert fmsg and ("Fett" in fmsg or "Stichflamme" in fmsg)


def test_feedback_useless_nudges_to_right_tool():
    msg = g.feedback_reason("F", "powder")               # powder on cooking oil = useless
    assert msg and g.right_tool_de("F") in msg           # names the wet-chemical extinguisher


def test_right_tool_is_actually_good():
    for c in g.FIRE_CLASSES:
        rt = g.right_tool_de(c["id"])
        # find the tool id whose German name is rt, and confirm it's 'good'
        tid = next(t["id"] for t in g.TOOLS if t["name_de"] == rt)
        assert g.MATRIX[c["id"]][tid] == "good"


# --- Layout: build spots must never overlap the path -------------------------

def test_build_spots_clear_the_path():
    ok, problems = g.check_levels()
    assert ok, "build spots overlap the path: " + "; ".join(problems)


def test_every_build_spot_has_clearance():
    for i in range(g.level_count()):
        lv = g.get_level(i)
        for (x, y) in lv["build_spots"]:
            d = g.point_to_path_distance(x, y, lv["path"])
            assert d >= g.BUILD_SPOT_CLEARANCE, f"level {i} spot ({x},{y}) only {d:.0f}px from path"


def test_check_levels_catches_a_spot_on_the_path(monkeypatch):
    lv = dict(g.LEVELS[0])
    lv["build_spots"] = [list(lv["path"][1])]      # a spot sitting exactly on a path point
    monkeypatch.setattr(g, "LEVELS", [lv])
    ok, problems = g.check_levels()
    assert not ok and problems


def test_point_to_path_distance_basic():
    path = [[0, 0], [100, 0]]
    assert abs(g.point_to_path_distance(50, 30, path) - 30) < 1e-6
    assert abs(g.point_to_path_distance(50, 0, path) - 0) < 1e-6


# --- ITEM-013: end-of-level recap + knowledge score --------------------------

def test_recap_after_a_clean_win():
    lv = _mini_level(budget=1000, waves=[{"gap": 0.6, "fires": ["A", "A", "A"]}])
    gs = g.GameState(lv); gs.place_tower(0, "water"); gs.place_tower(1, "water")
    for _ in range(100000):
        gs.advance(0.1)
        if gs.status != "playing":
            break
    r = gs.recap()
    assert r["status"] == "won"
    assert r["total"] == 3 and r["handled"] == 3 and r["knowledge"] == 100
    assert any(c["id"] == "A" and c["right_tool_de"] for c in r["classes"])


def test_recap_counts_leaks_mistakes_and_zero_knowledge():
    lv = _mini_level(budget=1000,
                     building={"x": 400, "y": 0, "lives": 2, "name_de": "X"},
                     waves=[{"gap": 0.5, "fires": ["electrical", "electrical", "electrical"]}])
    gs = g.GameState(lv); gs.place_tower(0, "water")   # water on electrical: never works
    for _ in range(100000):
        gs.advance(0.1)
        if gs.status != "playing":
            break
    r = gs.recap()
    assert r["status"] == "lost"
    assert r["leaked"] >= 2
    assert r["mistakes"] >= 1
    assert r["knowledge"] == 0


# --- ITEM-015: the first level is tuned so only safe, correct play wins -------
# These run the REAL level 0 ("Die Nacht des Fachwerkfeuers") with a player who
# buys the given towers as soon as the budget allows, then plays to the end.

def _play_level0(placements):
    """Run level 0 with an incremental player. placements: (spot_index, tool_id).
    Returns the recap dict."""
    gs = g.GameState(g.LEVELS[0])
    queue = list(placements)
    t = 0.0
    while gs.status == "playing" and t < 120:
        while queue and gs.place_tower(queue[0][0], queue[0][1])[0]:
            queue.pop(0)
        gs.advance(1 / 30.0)
        t += 1 / 30.0
    return gs.recap()


def test_level0_correct_play_wins_cleanly():
    # Powder handles Class A and electrical; the wet-chemical tool handles the
    # cooking-oil (F) fires. The right tool for every class = a clean win.
    r = _play_level0([(0, "powder"), (2, "wetchem")])
    assert r["status"] == "won", r
    assert r["leaked"] == 0, "correct play should not let any fire through"
    assert r["knowledge"] == 100


def test_level0_all_water_loses():
    r = _play_level0([(i, "water") for i in range(5)])
    assert r["status"] == "lost", "water is dangerous/useless on electrical and oil"


def test_level0_ignoring_cooking_oil_loses():
    # An all-powder defence puts out the solids and electrical fires but does
    # nothing to the three cooking-oil fires, which leak — so it must lose. This is
    # the level's core lesson: you cannot skip the fat-fire tool.
    r = _play_level0([(i, "powder") for i in range(5)])
    assert r["status"] == "lost", r
    assert r["leaked"] >= 3, "all three cooking-oil fires should leak through"


def test_level0_no_towers_loses():
    assert _play_level0([])["status"] == "lost"


def test_level0_has_the_three_taught_classes():
    seen = {ev["class"] for ev in g.build_schedule(g.LEVELS[0])}
    assert {"A", "electrical", "F"} <= seen


def test_behaviour_check_passes_on_the_shipped_level():
    ok, problems = g.behaviour_check()
    assert ok, "the shipped first level should only be won by safe play: " + "; ".join(problems)


# --- ITEM-016: the combined level + the gas/power shut-off mechanic -----------

def test_combined_level_exists_and_declares_supplies():
    lv2 = next((l for l in g.LEVELS if l.get("supplies")), None)
    assert lv2 is not None, "expected a level that declares supply hazards"
    assert set(lv2["supplies"]) == {"gas", "power"}
    seen = {ev["class"] for ev in g.build_schedule(lv2)}
    assert {"B", "C", "D"} <= seen, "combined level should teach liquids, gases, metals"


def test_gas_fire_ignores_spraying_until_the_supply_is_cut():
    lv = _mini_level(budget=1000, building={"x": 400, "y": 0, "lives": 9, "name_de": "X"},
                     supplies=["gas"], waves=[{"gap": 0.5, "fires": ["C"]}])
    gs = g.GameState(lv)
    gs.place_tower(0, "powder")            # powder is normally correct for gas
    for _ in range(60):
        gs.advance(0.1)
        if not gs.fires and gs.spawned:
            break
    # While the supply is on, spraying does nothing: no extinguish, at least one wasted shot.
    assert gs.stats["extinguished"] == 0
    assert gs.stats["useless_hits"] >= 1


def test_shutting_off_the_supply_puts_out_its_fires():
    lv = _mini_level(budget=0, building={"x": 400, "y": 0, "lives": 9, "name_de": "X"},
                     supplies=["gas"], waves=[{"gap": 0.5, "fires": ["C", "C"]}])
    gs = g.GameState(lv)
    for _ in range(25):                     # let both gas fires appear
        gs.advance(0.1)
    assert any(f["class"] == "C" for f in gs.fires)
    n = gs.shut_off("gas")
    assert n >= 1
    assert not any(f["class"] == "C" for f in gs.fires), "cutting the gas should clear gas fires"
    # A fire that spawns after the supply is cut never becomes a threat.
    assert gs.supplies["gas"] == "off"


def test_power_fire_needs_the_power_cut():
    lv = _mini_level(budget=1000, building={"x": 400, "y": 0, "lives": 9, "name_de": "X"},
                     supplies=["power"], waves=[{"gap": 0.5, "fires": ["electrical"]}])
    gs = g.GameState(lv)
    gs.place_tower(0, "co2")               # co2 is normally correct for electrical
    for _ in range(30):
        gs.advance(0.1)
    assert gs.stats["extinguished"] == 0   # spraying live electrical does nothing here
    gs.shut_off("power")
    assert not any(f["class"] == "electrical" for f in gs.fires)


def test_level1_electrical_still_works_without_a_power_switch():
    # Regression: the first level declares no supplies, so electrical is handled by
    # the right extinguisher exactly as before (the shut-off mechanic is opt-in).
    assert not g.LEVELS[0].get("supplies")
    lv = _mini_level(budget=1000, building={"x": 400, "y": 0, "lives": 9, "name_de": "X"},
                     waves=[{"gap": 0.5, "fires": ["electrical"]}])
    gs = g.GameState(lv)
    gs.place_tower(0, "co2")
    for _ in range(30):
        gs.advance(0.1)
        if not gs.fires and gs.spawned:
            break
    assert gs.stats["extinguished"] == 1   # co2 puts out electrical when there's no switch


def test_recap_right_action_uses_the_shut_off_for_gated_classes():
    lv2 = next(l for l in g.LEVELS if l.get("supplies"))
    r = g.GameState(lv2).recap()
    by_id = {c["id"]: c for c in r["classes"]}
    assert by_id["C"]["right_tool_de"] == g.HAZARD_ACTION_DE["gas"]
    assert by_id["electrical"]["right_tool_de"] == g.HAZARD_ACTION_DE["power"]


def test_burning_metal_only_yields_to_metal_powder():
    lv = _mini_level(budget=1000, building={"x": 400, "y": 0, "lives": 2, "name_de": "X"},
                     waves=[{"gap": 0.5, "fires": ["D", "D", "D"]}])
    gs = g.GameState(lv)
    gs.place_tower(0, "water"); gs.place_tower(1, "water")   # water is dangerous on metal
    for _ in range(300):
        gs.advance(0.1)
        if gs.status != "playing":
            break
    assert gs.status == "lost"


# --- ITEM-017: only safe play wins; difficulty grows gently -------------------

def _spam(level, tool):
    st = g.GameState(level); st.status = "playing"
    spots = len(level.get("build_spots", []))
    queue = [(s, tool) for s in range(spots)]
    t = 0.0
    while st.status == "playing" and t < 180:
        while queue and st.place_tower(queue[0][0], queue[0][1])[0]:
            queue.pop(0)
        st.advance(1 / 30.0)
        t += 1 / 30.0
    return st.status


def test_no_single_tool_spam_wins_any_level():
    for i in range(g.level_count()):
        lv = g.LEVELS[i]
        for t in g.TOOLS:
            assert _spam(lv, t["id"]) == "lost", \
                f"level {i} can be won by spamming {t['id']} — unsafe play must not win"


def test_second_level_won_by_a_correct_mix():
    lv = g.LEVELS[1]
    st = g.GameState(lv); st.status = "playing"
    queue = [(0, "powder"), (2, "wetchem")]
    t = 0.0
    while st.status == "playing" and t < 180:
        while queue and st.place_tower(queue[0][0], queue[0][1])[0]:
            queue.pop(0)
        st.advance(1 / 30.0)
        t += 1 / 30.0
    r = st.recap()
    assert r["status"] == "won" and r["leaked"] == 0


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


def test_ideal_tool_earns_more_than_an_acceptable_one():
    # Using the ideal ("good") tool is clearly better than a merely-acceptable
    # ("weak") one: it earns the smart-play bonus on top of the base reward.
    assert g.SMART_BONUS > 0


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


def test_new_missions_only_won_by_safe_play():
    # behaviour_check now plays each new mission; this asserts it stays green.
    ok, problems = g.behaviour_check()
    assert ok, "; ".join(problems)


def test_every_campaign_mission_has_antons_framing():
    for m in g.campaign_missions():
        lines = g.mission_lines_de(m["key"])
        for field in ("open", "anecdote", "hint", "close"):
            assert lines.get(field, "").strip(), f"{m['key']} missing Anton's {field}"


def test_narration_guard_passes_on_shipped_hints():
    ok, problems = g.check_narration()
    assert ok, "; ".join(problems)


def test_narration_guard_catches_a_dangerous_recommendation(monkeypatch):
    # Flip a hint to positively recommend a dangerous tool and confirm it's caught.
    bad = {k: dict(v) for k, v in g.ANTON["missions"].items()}
    bad["bibliothek"] = dict(bad["bibliothek"])
    bad["bibliothek"]["hint"] = g.L("Nimm einfach Wasser auf die alte Leitung.")
    monkeypatch.setitem(g.ANTON, "missions", bad)
    ok, problems = g.check_narration()
    assert not ok
    assert any("bibliothek" in p and "water" in p for p in problems)
