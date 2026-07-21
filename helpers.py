"""Shared test helpers — small builders and play-drivers used across the test
files. Not collected by pytest (no test_ prefix). Split out of the old
test_app.py (Step C)."""

import firefighter_defense as g

__all__ = [
    "_mini_level",
    "_shot",
    "_play_level0",
    "_spam",
    "_landscape_block",
]


# --- ITEM-009: towers, budget, auto-target, earn-back ------------------------

def _mini_level(**kw):
    lv = {"name": "t", "place_de": "t", "size": {"w": 400, "h": 100},
          "path": [[0, 0], [400, 0]], "build_spots": [[100, 0], [300, 0]],
          "building": {"x": 400, "y": 0, "lives": 3, "name_de": "X"},
          "budget": 100, "waves": []}
    lv.update(kw)
    return lv


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


# --- ITEM-057: "Version A" phone-landscape refinement (side strip + pre-game) --
# Light drift guards on the generated page string, matching the Option-B style
# above: they assert the landscape media query lays #toolPalette out as a vertical
# side strip, the inline #hint is hidden there, the dismissible pre-game overlay
# exists with its "Los geht's" control, and the matchMedia landscape guard is used
# to gate showing it (so desktop never sees it). Desktop/portrait are unaffected.

def _landscape_block(html):
    # The CSS inside the phone-landscape media query, up to its closing (the next
    # "</style>"). Used to prove rules live INSIDE the landscape query only.
    after = html.split("@media (orientation: landscape) and (max-height: 500px)", 1)[1]
    return after.split("</style>", 1)[0]
