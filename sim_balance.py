"""ITEM-015 balance simulation for level 0. Not shipped — a tuning aid.
Runs the real GameState with different tower strategies and level dials, so we can
choose lives/budget where correct play wins and lazy/unsafe play loses."""
from __future__ import annotations
import copy
import sys
import types


def _shim_fastapi():
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


_shim_fastapi()
import firefighter_defense as g

DT = 1 / 30.0


def run(level: dict, placements: list, incremental: bool = False) -> dict:
    """placements: list of (spot_index, tool_id).
    incremental=False: place all at t=0 (fails if can't afford upfront).
    incremental=True: place each as soon as budget allows while the level runs
    (mimics a real player who buys towers with earned-back budget)."""
    st = g.GameState(level)
    if not incremental:
        for spot, tool in placements:
            ok, why = st.place_tower(spot, tool)
            if not ok:
                return {"error": f"place {tool}@{spot}: {why}"}
        t = 0.0
        while st.status == "playing" and t < 120:
            st.advance(DT)
            t += DT
    else:
        queue = list(placements)
        t = 0.0
        while st.status == "playing" and t < 120:
            # buy whatever we can afford, in order
            while queue and st.place_tower(queue[0][0], queue[0][1])[0]:
                queue.pop(0)
            st.advance(DT)
            t += DT
    r = st.recap()
    r["budget_left"] = st.budget
    r["unplaced"] = len(placements) - len(st.towers)
    return r


def class_counts(level):
    from collections import Counter
    c = Counter(ev["class"] for ev in g.build_schedule(level))
    return dict(c)


def coverage(level):
    """For each build spot, which path fraction it can reach — helps pick placements."""
    out = []
    spots = level["build_spots"]
    path = level["path"]
    for i, (sx, sy) in enumerate(spots):
        hits = 0
        steps = 200
        for k in range(steps + 1):
            px, py = g.path_point_at(path, k / steps)
            if ((px - sx) ** 2 + (py - sy) ** 2) ** 0.5 <= g.TOWER_RANGE:
                hits += 1
        out.append((i, round(100 * hits / (steps + 1))))
    return out


def scenarios(level):
    n = len(level["build_spots"])
    return {
        "no towers": [],
        "all water": [(i, "water") for i in range(n)],
        "all powder": [(i, "powder") for i in range(n)],
        # correct minimal: powder covers A + electrical; wetchem covers F.
        "powder+wetchem (min 2)": [(0, "powder"), (2, "wetchem")],
        "powder x2 + wetchem x2": [(0, "powder"), (1, "powder"), (2, "wetchem"), (3, "wetchem")],
        "full correct (all 5)": [(0, "powder"), (1, "powder"), (2, "wetchem"),
                                 (3, "powder"), (4, "wetchem")],
    }


def try_level(lives: int, budget: int):
    lv = copy.deepcopy(g.LEVELS[0])
    lv["building"]["lives"] = lives
    lv["budget"] = budget
    print(f"\n=== lives={lives} budget={budget} | classes={class_counts(lv)} | "
          f"spots={len(lv['build_spots'])} ===")
    print("    coverage (spot: % of path reachable):", coverage(lv))
    for name, placements in scenarios(lv).items():
        r = run(lv, placements, incremental=True)
        if "error" in r:
            print(f"    {name:26s} -> SKIP ({r['error']})")
            continue
        print(f"    {name:26s} -> {r['status']:4s}  know={r['knowledge']}%  "
              f"leaked={r['leaked']}  mistakes={r['mistakes']}  "
              f"budget_left={r['budget_left']}  unplaced={r['unplaced']}")


def run3(placements, cut=(), dt=1 / 30.0):
    """Level 2 (index 2) runner: place towers up front, optionally cut supplies at
    the start, then play to the end. cut is a tuple of 'gas'/'power'."""
    st = g.GameState(g.LEVELS[2])
    st.status = "playing"
    for h in cut:
        st.shut_off(h)
    for spot, tool in placements:
        st.place_tower(spot, tool)
    t = 0.0
    while st.status == "playing" and t < 120:
        st.advance(dt)
        t += dt
    r = st.recap()
    r["budget_left"] = st.budget
    r["towers"] = len(st.towers)
    return r


def try_level2():
    lv = g.LEVELS[2]
    print(f"\n=== LEVEL 2 '{lv['name']}' | lives={lv['building']['lives']} "
          f"budget={lv['budget']} | classes={class_counts(lv)} | supplies={lv['supplies']} ===")
    print("    coverage:", coverage(lv))
    scen = {
        "cut both + foam+metal": ([(1, "foam"), (4, "metal")], ("gas", "power")),
        "cut both + foam x2 + metal": ([(1, "foam"), (3, "foam"), (4, "metal")], ("gas", "power")),
        "cut both + powder + metal x2": ([(1, "powder"), (4, "metal"), (2, "metal")], ("gas", "power")),
        "cut both + foam + metal x2": ([(0, "foam"), (1, "foam"), (4, "metal"), (2, "metal")], ("gas", "power")),
        "forgot to cut (foam+metal only)": ([(1, "foam"), (4, "metal")], ()),
        "all water, cut both": ([(i, "water") for i in range(5)], ("gas", "power")),
        "no towers, cut both": ([], ("gas", "power")),
        "no towers, no cut": ([], ()),
    }
    for name, (pl, cut) in scen.items():
        r = run3(pl, cut)
        print(f"    {name:34s} -> {r['status']:4s}  know={r['knowledge']}%  "
              f"leaked={r['leaked']}  mistakes={r['mistakes']}  budget_left={r['budget_left']}  towers={r['towers']}")


if __name__ == "__main__":
    try_level2()
