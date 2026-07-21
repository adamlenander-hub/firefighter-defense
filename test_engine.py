"""Tests for GameState — play mechanics, towers, teaching resolution (engine.py)

Split out of the old test_app.py (Step C)."""

import firefighter_defense as g
from helpers import *  # shared test builders/play-drivers

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


def test_ideal_tool_earns_more_than_an_acceptable_one():
    # Using the ideal ("good") tool is clearly better than a merely-acceptable
    # ("weak") one: it earns the smart-play bonus on top of the base reward.
    assert g.SMART_BONUS > 0


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
