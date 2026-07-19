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


def test_sound_toggle_and_effects_are_wired():
    # ITEM-019: browser-generated sound with a German mute toggle, guarded so a
    # failure is silent. This checks the wiring exists in the page; loudness and
    # autoplay-unlock can only be judged by a real-browser listen.
    html = g.render_game_html()
    assert 'id="soundToggle"' in html          # the mute checkbox
    assert "> Ton<" in html                     # labelled in German, default checked
    assert "checkbox" in html and 'id="soundToggle" checked' in html
    assert "function playSound" in html         # the single guarded entry point
    assert "function initAudio" in html         # autoplay-safe unlock on user gesture
    assert "AudioContext" in html               # Web Audio API (no audio files)
    for cue in ("'good'", "'danger'", "'useless'", "'win'", "'lose'"):
        assert cue in html                      # every defined moment has a cue
    assert "fd_sound" in html                   # guarded localStorage persistence


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

def _shot(tool, cls, max_shots=1):
    """Fire up to `max_shots` tower shots of `tool` at a fire of class `cls` sitting
    on the tower (its position is pinned back between shots so only hit-resolution
    is under test, never dwell/range), stopping as soon as it's extinguished.
    Reports (game state, extinguished?, total budget earned).

    ITEM-041: a "good" tool still clears a fire in one shot (max_shots=1 is enough,
    matching every existing single-shot caller); a "weak" tool needs a caller to
    pass a bigger max_shots to see it fully wear the fire down."""
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, tool)                       # tower at (100,0)
    gs.fires = [{"id": 1, "class": cls, "progress": 0.25, "hp": g.FIRE_HP}]  # (100,0), in range
    b0 = gs.budget
    for _ in range(max_shots):
        gs.advance(g.TOWER_COOLDOWN + 0.01)       # guarantees exactly one shot per call
        if all(f["id"] != 1 for f in gs.fires):
            break
        for f in gs.fires:
            if f["id"] == 1:
                f["progress"] = 0.25              # hold position between shots
    extinguished = all(f["id"] != 1 for f in gs.fires)
    return gs, extinguished, gs.budget - b0


def test_resolution_matches_the_matrix_for_every_pair():
    for cls, row in g.MATRIX.items():
        for tool, expected in row.items():
            # ITEM-041: a "weak" (acceptable) tool may need a second hit to fully
            # wear a fire down — a "good" (ideal) one still does it in the first.
            gs, extinguished, earned = _shot(tool, cls, max_shots=4)
            if expected in ("good", "weak"):
                assert extinguished, f"{tool} on {cls} ({expected}) should put it out"
                assert earned == g.EXTINGUISH_REWARD + (g.SMART_BONUS if expected == "good" else 0)
            elif expected == "danger":
                assert not extinguished, f"{tool} on {cls} is dangerous — must NOT put it out"
                assert earned == 0
                assert gs.stats["danger_hits"] >= 1
            else:  # useless
                assert not extinguished, f"{tool} on {cls} is useless — must NOT put it out"
                assert earned == 0
                assert gs.stats["useless_hits"] >= 1


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
    """Run level 0 with a player who keeps the given (spot_index, tool_id) spots
    filled — buying, and (ITEM-040) re-buying once a tower runs out of charge —
    for as long as the budget allows. Returns the recap dict. Thin wrapper over the
    production `_play_out` helper so this test and the `--simulate` behaviour guard
    can never quietly drift apart."""
    return g._play_out(g.LEVELS[0], placements)


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
    # ITEM-040: uses _play_out (not a one-shot buy) so a tower that runs out of
    # charge partway through gets noticed and re-bought, same as a real safe player.
    r = g._play_out(g.LEVELS[1], [(0, "powder"), (2, "wetchem")])
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


def test_library_vignette_is_the_finds_his_name_beat():
    cap = g.vignette_de("bibliothek")["caption"]
    assert "Name" in cap or "name" in cap
    assert "Anton" in cap


def test_finale_delivers_the_closing_message():
    fin = g.finale_de()
    assert fin.get("scene") == "helmet"
    assert len(fin.get("lines", [])) >= 3
    blob = " ".join(fin["lines"])
    # courage, compassion and community matter more than equipment
    assert "Mut" in blob and "Mitgefühl" in blob and "Zusammenhalt" in blob
    assert "Ausrüstung" in blob
    # the helmet (Feuerwehrmütze) hand-over is present
    assert "Feuerwehrmütze" in fin.get("caption", "")


def test_arc_and_finale_do_not_change_any_fire_fact_or_level():
    # ITEM-028 is narrative only: the matrix and every level's waves/budget/lives are
    # untouched, and the safe-play guard still holds.
    ok, problems = g.check_content()
    assert ok, problems
    ok2, problems2 = g.behaviour_check()
    assert ok2, "; ".join(problems2)


# --- ITEM-038: two-tone flat art direction (visual only) ----------------------

def test_flat_palette_and_helpers_present_in_page():
    html = g.render_game_html()
    # the approved flat palette as CSS variables, for both themes
    assert "--a:#f59e0b" in html and "--e:#2f6fed" in html          # :root light
    assert "--a:#ffc247" in html and "--panel:#161a22" in html      # body.hc dark
    # the shared two-tone helpers the later visual items reuse
    assert "function shade(" in html and "function rr(" in html
    assert "function skyGradient(" in html                          # sky gradient computed once
    # panels/canvas reskinned to the flat rounded look
    assert "border-radius: 22px" in html


def test_high_contrast_still_overrides_to_a_dark_field():
    # The high-contrast toggle (ITEM-020) must still switch to a plain dark field.
    html = g.render_game_html()
    assert "body.hc{" in html
    assert "--page:#0b0d12" in html            # dark page background variable
    assert 'id="contrastToggle"' in html       # the toggle is still present


def test_visual_reskin_changed_no_fire_fact_or_balance():
    # ITEM-038 is visual only — the matrix and safe-play guards are unchanged.
    ok, problems = g.check_content()
    assert ok, problems
    ok2, problems2 = g.behaviour_check()
    assert ok2, "; ".join(problems2)


# --- ITEM-039: distinctive animated fire characters (visual only) -------------

def test_per_type_fire_characters_present():
    html = g.render_game_html()
    assert "function drawFireCharacter(" in html
    assert "function drawEvilFace(" in html and "function drawFlameBody(" in html
    # a distinct branch for each animated type Adam named + the judgement-call ones
    for branch in ("cls==='F'", "cls==='B'", "cls==='electrical'", "cls==='D'", "cls==='C'"):
        assert branch in html, branch


def test_fire_characters_keep_greyscale_safe_signalling():
    # The class LETTER badge, emoji icon, and reaction-ring shapes must still be drawn
    # (ITEM-008) — the character art is decoration on top, never a replacement.
    html = g.render_game_html()
    fire = html[html.index("function drawFire(f){"):html.index("function drawOverlay")]
    assert "cls.letter" in fire                     # letter badge
    assert "cls.icon" in fire                       # emoji icon
    assert "#b91c1c" in fire and "setLineDash([4,4])" in fire   # danger (solid red) + useless (dashed) rings
    assert "⚠" in fire                          # ⚠️ danger glyph


def test_fire_characters_changed_no_fire_fact_or_balance():
    ok, problems = g.check_content()
    assert ok, problems
    ok2, problems2 = g.behaviour_check()
    assert ok2, "; ".join(problems2)


# --- ITEM-044 / 035 / 036: per-mission path + background + extinguisher palette --

def test_per_mission_path_materials_present():
    html = g.render_game_html()
    for fn in ("drawPathTimber", "drawPathBooks", "drawPathGravel", "drawPathChips", "drawPathCables"):
        assert "function " + fn + "(" in html, fn
    # dispatched by the level key, and path motifs are cached (computed once, not per frame)
    assert "key==='fachwerk'" in html and "key==='schlosserei'" in html
    assert "_motifCache" in html


def test_per_mission_backgrounds_present_and_dark_in_high_contrast():
    html = g.render_game_html()
    for fn in ("bgFachwerk", "bgBibliothek", "bgKurpark", "bgFeuerwerk", "bgSchlosserei"):
        assert "function " + fn + "(" in html, fn
    # per-level gradient cached (computed once), and a plain dark field in high-contrast
    assert "_bgKey" in html and "function bgGradient(" in html
    assert "if (contrastEnabled){ ctx.fillStyle='#0b0d12'" in html


def test_palette_shows_extinguisher_graphic_and_info_popup():
    html = g.render_game_html()
    # tool cards with a canvas graphic + label + info affordance
    assert "class=\"toolbtn\"" not in html  # built in JS, not static markup
    assert "'toolbtn'" in html and "'toolcv'" in html and "'toolinfo'" in html
    assert "function openToolInfo(" in html and 'id="toolInfo"' in html
    # selecting a tool still selects it for placement (game action preserved)
    assert "selectedTool=t.id" in html
    # info text is derived from the guarded matrix (no invented facts)
    assert "matrixMap[cid" in html
    # still keyboard-selectable (1..N) via the existing slot handler
    assert "function selectToolSlot(" in html


def test_path_bg_palette_changes_touch_no_fire_fact_or_balance():
    ok, problems = g.check_content()
    assert ok, problems
    ok2, problems2 = g.behaviour_check()
    assert ok2, "; ".join(problems2)


# --- ITEM-041: fires resist being put out (different put-out times per tool) ---

def test_good_tool_still_clears_a_fire_in_a_single_hit():
    # The ideal tool must stay instant — earlier place/dwell-time tuning (e.g. the
    # feuerwerk stage's metal-powder tower) depends on a "good" hit clearing a fire
    # in one shot, exactly as before this item.
    gs, extinguished, earned = _shot("water", "A")   # water is "good" on Class A
    assert extinguished
    assert earned == g.EXTINGUISH_REWARD + g.SMART_BONUS


def test_weak_tool_needs_more_than_one_hit_and_still_wins_the_fire():
    # co2 on Class A is "weak" (acceptable, not ideal): it must NOT clear the fire
    # on the first hit, but must still finish it off (and earn only the base
    # reward — no smart-play bonus) within a few hits.
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, "co2")
    gs.fires = [{"id": 1, "class": "A", "progress": 0.25, "hp": g.FIRE_HP}]
    b0 = gs.budget
    gs.advance(0.02)                       # first shot lands ...
    assert any(f["id"] == 1 for f in gs.fires), "a weak tool should NOT clear a fire in one hit"
    assert gs.fires[0]["hp"] < g.FIRE_HP, "the fire should visibly be worn down after one weak hit"
    gs.fires[0]["progress"] = 0.25          # hold position for the second shot
    gs.advance(g.TOWER_COOLDOWN + 0.01)     # ... second shot finishes it
    assert all(f["id"] != 1 for f in gs.fires)
    assert gs.budget - b0 == g.EXTINGUISH_REWARD, "a weak tool earns no smart-play bonus"


def test_useless_and_dangerous_tools_never_reduce_hp_no_matter_how_long():
    # Hard invariant: wrong/dangerous tools must never extinguish a fire, at any
    # duration. Confirm this holds for hp specifically (ITEM-041's new field), not
    # just for the fire being removed.
    for tool, cls in (("metal", "A"), ("water", "electrical")):
        gs = g.GameState(_mini_level(budget=1000))
        gs.place_tower(0, tool)
        gs.fires = [{"id": 1, "class": cls, "progress": 0.25, "hp": g.FIRE_HP}]
        for _ in range(20):
            gs.advance(g.TOWER_COOLDOWN + 0.01)
            for f in gs.fires:
                if f["id"] == 1:
                    f["progress"] = 0.25
        assert any(f["id"] == 1 for f in gs.fires), f"{tool} on {cls} must never extinguish the fire"
        remaining = next(f for f in gs.fires if f["id"] == 1)
        assert remaining["hp"] == g.FIRE_HP, f"{tool} on {cls} must never wear the fire's hp down"


def test_fire_resistance_is_drawn_shrinking_toward_the_kill():
    html = g.render_game_html()
    assert "FIRE_HP" in html and "GOOD_HIT_DAMAGE" in html and "WEAK_HIT_DAMAGE" in html
    assert "flameScale" in html   # the flame character shrinks with remaining hp (base-anchored, merged with ITEM-051)


# --- ITEM-040: extinguishers deplete and empty out ---------------------------

def test_freshly_placed_tower_has_charge_and_it_is_spent_on_effective_shots():
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, "water")
    tw = gs.towers[0]
    assert tw["charge"] == tw["max_charge"] > 0
    gs.fires = [{"id": 1, "class": "A", "progress": 0.25, "hp": g.FIRE_HP}]  # water is good on A
    gs.advance(0.02)
    assert gs.towers[0]["charge"] == tw["max_charge"] - 1


def test_tower_is_removed_once_charge_runs_out_freeing_the_spot():
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, "water")
    charge = gs.towers[0]["charge"]
    # Keep a fresh Class A fire (water is good) sitting on the tower and let it
    # fire repeatedly until the canister is empty. (_mini_level's default empty
    # waves means the level would otherwise flip to "won" the instant no fire is
    # left — force it back to "playing" each round so the test purely exercises
    # charge depletion.)
    for i in range(charge):
        gs.status = "playing"
        gs.fires = [{"id": 100 + i, "class": "A", "progress": 0.25, "hp": g.FIRE_HP}]
        gs.advance(g.TOWER_COOLDOWN + 0.01)
    assert gs.towers == [], "a tower should be removed once its charge reaches zero"
    # The spot is free again — a new tower can be bought there.
    ok, why = gs.place_tower(0, "foam")
    assert ok, why


def test_useless_shot_does_not_spend_charge():
    # A shot that plainly can't touch this class of fire (e.g. metal powder is
    # useless on Class C gases) shouldn't bankrupt a tower that's simply standing
    # near an unrelated fire — only a shot that actually discharges AT the fire
    # (good/weak/dangerous) spends charge.
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, "metal")
    charge0 = gs.towers[0]["charge"]
    gs.fires = [{"id": 1, "class": "C", "progress": 0.25, "hp": g.FIRE_HP}]  # metal is useless on C
    for _ in range(5):
        gs.advance(g.TOWER_COOLDOWN + 0.01)
        gs.fires = [{"id": 1, "class": "C", "progress": 0.25, "hp": g.FIRE_HP}]
    assert gs.stats["useless_hits"] >= 1
    assert gs.towers[0]["charge"] == charge0, "a wholly useless shot must not spend charge"


def test_dangerous_shot_spends_charge_same_as_a_correct_one():
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, "water")
    charge0 = gs.towers[0]["charge"]
    gs.fires = [{"id": 1, "class": "electrical", "progress": 0.25, "hp": g.FIRE_HP}]  # water is dangerous
    gs.advance(0.02)
    assert gs.towers[0]["charge"] == charge0 - 1, "a dangerous shot still discharges the extinguisher"


def test_charge_tightens_across_the_four_campaign_missions():
    charges = [g.tower_charge_for(m) for m in ({"mission": 1}, {"mission": 2}, {"mission": 3}, {"mission": 4})]
    assert charges[0] > charges[1] > charges[2] > charges[3], charges
    assert charges[0] == g.TOWER_CHARGE_BASE
    assert all(c >= g.MIN_TOWER_CHARGE for c in charges)


def test_non_campaign_levels_use_the_generous_baseline_charge():
    non_campaign = next(lv for lv in g.LEVELS if not lv.get("campaign"))
    assert g.tower_charge_for(non_campaign) == g.TOWER_CHARGE_BASE == g.tower_charge_for({"mission": 1})


def test_charge_gauge_is_drawn_on_the_tower():
    html = g.render_game_html()
    assert "towerChargeFor" in html and "maxCharge" in html


def test_extinguisher_bigger_and_gauge_vertical_on_the_right():
    # ITEM-055: the placed extinguisher is drawn 50% bigger (26x36 -> 39x54).
    # ITEM-054: the charge gauge is a vertical bar to the RIGHT of the extinguisher,
    # not a horizontal bar underneath it.
    html = g.render_game_html()
    tower = html[html.index("function drawTower(tw){"):html.index("function drawSprays")]
    assert "var w=39, h=54" in tower            # ITEM-055: 1.5x bigger extinguisher
    assert "x + w/2 + 4" in tower               # ITEM-054: gauge positioned to the right
    assert "gh=h*0.82" in tower                 # ITEM-054: gauge is tall (vertical), not a 5px-high bar


def test_build_spot_is_solid_black_with_white_border_in_all_modes():
    # ITEM-056 (replaces ITEM-049): an open build spot is a solid black circle with a
    # white border, drawn identically whether high-contrast is on or off.
    html = g.render_game_html()
    spot = html[html.index("function drawBuildSpot(x,y){"):html.index("function drawKeyHighlight")]
    assert "fillStyle='#000000'" in spot and "arc(x,y,24" in spot   # solid black disc
    assert "strokeStyle='#ffffff'" in spot                          # white border
    assert "contrastEnabled" not in spot                            # same in all modes (no per-mode branch)


# --- ITEM-034: water on liquid(B)/cooking-oil(F) fires splits them ------------

def test_water_on_a_liquid_fire_can_split_it_in_two():
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, "water")
    gs.fires = [{"id": 1, "class": "B", "progress": 0.25, "hp": g.FIRE_HP}]  # water is dangerous on B
    before = len(gs.fires)
    gs.advance(0.02)
    assert len(gs.fires) == before + 1, "a dangerous water hit on a liquid fire should split it"
    assert all(f["class"] == "B" for f in gs.fires)
    assert gs.stats["danger_hits"] == 1


def test_water_on_a_cooking_oil_fire_can_split_it_too():
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, "water")
    gs.fires = [{"id": 1, "class": "F", "progress": 0.25, "hp": g.FIRE_HP}]  # water is dangerous on F
    gs.advance(0.02)
    assert len(gs.fires) == 2
    assert all(f["class"] == "F" for f in gs.fires)


def test_splitting_never_exceeds_the_max_active_fires_cap():
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, "water")
    gs.fires = [
        {"id": i, "class": "B", "progress": 0.25, "hp": g.FIRE_HP}
        for i in range(g.MAX_ACTIVE_FIRES)
    ]
    gs.advance(0.02)
    assert len(gs.fires) <= g.MAX_ACTIVE_FIRES, "splitting must never push past the fire cap"


def test_split_fires_are_still_only_cleared_by_the_correct_tool():
    # A split fire is a fresh, ordinary fire of the same class — the matrix still
    # applies to it exactly the same (wrong tools never clear it).
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, "water")
    gs.fires = [{"id": 1, "class": "B", "progress": 0.25, "hp": g.FIRE_HP}]
    gs.advance(0.02)
    assert len(gs.fires) == 2
    for f in gs.fires:
        f["progress"] = 0.25
    gs.advance(0.02)   # water again: still dangerous, never extinguishes either copy
    assert len(gs.fires) >= 2


# --- ITEM-042: switch off / remove a wrongly-placed extinguisher -------------

def test_remove_tower_frees_the_spot_with_no_refund():
    gs = g.GameState(_mini_level(budget=1000))
    gs.place_tower(0, "water")
    budget_after_buy = gs.budget
    assert len(gs.towers) == 1
    removed = gs.remove_tower(0)
    assert removed is True
    assert gs.towers == []
    assert gs.budget == budget_after_buy, "removing a tower must NOT refund its cost"
    # The spot is free again.
    ok, why = gs.place_tower(0, "foam")
    assert ok, why


def test_remove_tower_on_an_empty_spot_is_a_no_op():
    gs = g.GameState(_mini_level(budget=1000))
    assert gs.remove_tower(0) is False
    assert gs.towers == []


def test_removal_cannot_be_used_to_cheese_a_win():
    # Buying, removing, and re-buying a tool over and over must never manufacture
    # budget out of nothing (no refund on removal).
    gs = g.GameState(_mini_level(budget=200))
    b0 = gs.budget
    for _ in range(3):
        gs.place_tower(0, "water")
        gs.remove_tower(0)
    assert gs.budget == b0 - 3 * g.tool_cost("water")


def test_remove_tower_reachable_by_touch_and_keyboard_in_js():
    html = g.render_game_html()
    assert "function removeTower(spotIndex)" in html
    # touch/click path: tapping an occupied spot with no tool selected removes it,
    # kept distinct from placeTower's own logic (ITEM-042 requirement).
    assert "function boardTapAt(" in html
    assert "towerAt(i)){ keyIndex=i; removeTower(i); }" in html
    # keyboard parity (ITEM-020): Delete/Backspace removes the highlighted tower.
    assert "k==='Delete'||k==='Backspace'" in html


# --- ITEM-033: house damage stages + Anton flees (visual/narration only) ------

def test_building_damage_stage_reflects_remaining_lives_in_js():
    html = g.render_game_html()
    assert "function buildingDamageStage()" in html
    assert "function drawSmokeRuin(" in html and "function drawCracksAndLick(" in html


def test_anton_worry_and_flee_are_present_and_separate_from_bravery_in_js():
    html = g.render_game_html()
    assert "function antonWorryFactor()" in html
    assert "function antonBraveryFactor()" in html
    # worry is driven by THIS level's lives, not by campaign/win progress
    assert "game.lives / start" in html
    # Anton flees once lives hit zero, and his win-side helmet/finale arc is
    # unaffected: antonWearsHelmet() still depends only on campaignProgress.
    assert "game.lives<=0 && game.fledAt" in html
    assert "function antonWearsHelmet(){\n      var tot = campaignTotal() || 4;\n      return campaignProgress >= tot;" in html


def test_visual_damage_mechanic_does_not_change_the_lose_condition():
    # ITEM-033 is presentation only: lives<=0 is still exactly when a level is lost.
    lv = _mini_level(budget=0, building={"x": 400, "y": 0, "lives": 1, "name_de": "X"},
                     waves=[{"gap": 0.5, "fires": ["A"]}])
    gs = g.GameState(lv)
    for _ in range(200):
        gs.advance(0.1)
        if gs.status != "playing":
            break
    assert gs.status == "lost" and gs.lives == 0
