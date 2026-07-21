"""GameState — the framework-free, deterministic play engine (ITEM-007+)."""
from __future__ import annotations

from config import *
from content import *
from levels import *
from levels import _path_length  # underscored, so not pulled in by `import *`

class GameState:
    """The running state of one level: which fires are on the path, how many lives
    are left, and whether the level is still playing / won / lost. Framework-free
    and deterministic, so the game loop can be tested without a browser. The browser
    mirrors this same logic to draw it."""

    def __init__(self, level: dict, matrix: dict = None):
        self.level = level
        self.schedule = build_schedule(level)
        path_len = _path_length(level["path"])
        self.speed = (FIRE_PX_PER_SEC / path_len) if path_len else 0.0  # progress per second
        self.lives = level["building"]["lives"]
        self.elapsed = 0.0
        self.spawned = 0
        self.fires = []          # each: {"id", "class", "progress"}
        self._next_id = 0
        self.status = "playing"  # "playing" | "won" | "lost"
        self.budget = level.get("budget", 0)
        self.towers = []         # each: {"id","spot_index","spot","tool","cooldown"}
        self._next_tower_id = 0
        # The fire-safety matrix the game resolves shots against. Defaults to the
        # source-of-truth constant; the real app loads it from the database (same
        # data, guarded by the content check). Passed in so tests are deterministic.
        self.matrix = matrix if matrix is not None else {
            (c, t): o for c, row in MATRIX.items() for t, o in row.items()
        }
        self.stats = {"extinguished": 0, "useless_hits": 0, "danger_hits": 0}
        self.leaked = 0          # fires that reached the building (ITEM-013)
        # Supply hazards this level opts into (ITEM-016): each starts "on" and can be
        # cut off. _gated_class maps a fire class to the hazard that must be cut before
        # it can be dealt with (gas -> "C", power -> "electrical").
        self.supplies = {h: "on" for h in level.get("supplies", [])}
        self._gated_class = {HAZARD_CLASS[h]: h for h in self.supplies if h in HAZARD_CLASS}

    def advance(self, dt: float) -> None:
        if self.status != "playing":
            return
        self.elapsed += dt
        # Spawn any fires whose time has come.
        while self.spawned < len(self.schedule) and self.schedule[self.spawned]["t"] <= self.elapsed:
            ev = self.schedule[self.spawned]
            cls = ev["class"]
            haz = self._gated_class.get(cls)
            if haz and self.supplies.get(haz) == "off":
                # Its supply is already cut, so this fire can't sustain — it never
                # really starts. Count it as handled (the player did the right thing).
                self.stats["extinguished"] += 1
                self.spawned += 1
                continue
            self.fires.append({"id": self._next_id, "class": cls, "progress": 0.0, "hp": FIRE_HP})
            self._next_id += 1
            self.spawned += 1
        # Towers fire at the nearest fire in range. The outcome depends on whether the
        # tool is right for that fire class (ITEM-010), read from the fire-safety
        # matrix — so the only way to clear a level is to use safe, correct tools.
        for tw in self.towers:
            tw["cooldown"] -= dt
            if tw["cooldown"] > 0:
                continue
            target = self._nearest_fire_in_range(tw)
            if target is None:
                continue
            tw["cooldown"] = TOWER_COOLDOWN
            haz = self._gated_class.get(target["class"])
            if haz and self.supplies.get(haz) == "on":
                # The supply is still on: spraying does nothing. The lesson is to cut
                # the supply first (the browser shows Anton's warning). Nothing was
                # actually discharged at a fire that could react to it, so — ITEM-040 —
                # no charge is spent (a fire the tool can't touch at all doesn't drain
                # the canister; see the charge comment above for the full rule).
                target["reaction"] = "useless"
                self.stats["useless_hits"] += 1
                continue
            outcome = self.matrix.get((target["class"], tw["tool"]))
            if outcome in ("good", "weak"):
                # ITEM-040: this shot actually did something to the fire, so it costs
                # a charge. ITEM-041: a correct hit wears the fire's resistance down
                # rather than clearing it outright — the ideal ("good") tool still
                # does it in one hit, the merely acceptable ("weak") one needs
                # another. Reward + smart-play bonus are only paid out on the actual
                # put-out.
                tw["charge"] -= 1
                target["hp"] = target.get("hp", FIRE_HP) - (GOOD_HIT_DAMAGE if outcome == "good" else WEAK_HIT_DAMAGE)
                if target["hp"] <= 1e-9:
                    self.fires = [f for f in self.fires if f["id"] != target["id"]]
                    self.budget += EXTINGUISH_REWARD + (SMART_BONUS if outcome == "good" else 0)
                    self.stats["extinguished"] += 1
                else:
                    target["reaction"] = "hit"
            elif outcome == "danger":
                # Dangerous mismatch (e.g. water on electrical or on cooking oil):
                # it backfires — the fire flares and lurches toward the building. No
                # budget. This is the strongest teaching moment. ITEM-040: a
                # dangerous mismatch DID discharge the extinguisher (just badly), so
                # it costs a charge too — the wrong choice is never cheaper.
                tw["charge"] -= 1
                target["progress"] = min(0.999, target["progress"] + DANGER_SPEEDUP)
                target["reaction"] = "danger"
                self.stats["danger_hits"] += 1
                # ITEM-034: water thrown on a liquid or cooking-oil fire can split it
                # in two — a second dramatization of "never water on B/F" — capped so
                # a chain of splits can never make a level unwinnable.
                if tw["tool"] == "water" and target["class"] in ("B", "F") and len(self.fires) < MAX_ACTIVE_FIRES:
                    self.fires.append({
                        "id": self._next_id, "class": target["class"],
                        "progress": max(0.0, target["progress"] - 0.05), "hp": FIRE_HP,
                    })
                    self._next_id += 1
            else:
                # Useless tool: nothing happens, the shot is wasted, no budget, and
                # (ITEM-040) no charge — an extinguisher that plainly can't touch this
                # class of fire is never even discharged.
                target["reaction"] = "useless"
                self.stats["useless_hits"] += 1
        # ITEM-040: a tower with no charge left is spent — remove it and free the spot.
        self.towers = [tw for tw in self.towers if tw["charge"] > 0]
        # Move fires; any that reach the building cost a life and are removed.
        still = []
        for f in self.fires:
            f["progress"] += self.speed * dt
            if f["progress"] >= 1.0:
                self.lives -= 1
                self.leaked += 1
            else:
                still.append(f)
        self.fires = still
        if self.lives <= 0:
            self.lives = 0
            self.status = "lost"
            return
        # Won when every scheduled fire has spawned and none are left on the path.
        if self.spawned >= len(self.schedule) and not self.fires:
            self.status = "won"

    def extinguish(self, fire_id: int) -> bool:
        """Remove a fire without costing a life. Towers call this via advance();
        tests use it to simulate a successful defence."""
        before = len(self.fires)
        self.fires = [f for f in self.fires if f["id"] != fire_id]
        return len(self.fires) < before

    def place_tower(self, spot_index: int, tool_id: str) -> tuple:
        """Try to place a tower of tool_id on build spot spot_index. Returns
        (ok, reason). Fails if the spot is out of range, already taken, the tool is
        unknown, or the budget can't afford it."""
        spots = self.level.get("build_spots", [])
        if not (0 <= spot_index < len(spots)):
            return (False, "no such build spot")
        if any(tw["spot_index"] == spot_index for tw in self.towers):
            return (False, "that spot is already taken")
        cost = tool_cost(tool_id)
        if cost <= 0:
            return (False, "unknown tool")
        if self.budget < cost:
            return (False, "not enough budget")
        self.budget -= cost
        charge = tower_charge_for(self.level)
        self.towers.append({
            "id": self._next_tower_id, "spot_index": spot_index,
            "spot": spots[spot_index], "tool": tool_id, "cooldown": 0.0,
            "charge": charge, "max_charge": charge,   # ITEM-040: limited shots
        })
        self._next_tower_id += 1
        return (True, "ok")

    def remove_tower(self, spot_index: int) -> bool:
        """ITEM-042: switch off / remove a (possibly wrongly-placed) extinguisher,
        freeing its spot. NO REFUND — spent money is gone, on purpose (Adam's
        decision), so removal can never be used to cheese a win by recycling budget.
        Returns True if a tower was actually removed."""
        before = len(self.towers)
        self.towers = [tw for tw in self.towers if tw["spot_index"] != spot_index]
        return len(self.towers) < before

    def shut_off(self, hazard: str) -> int:
        """Cut a supply (ITEM-016): 'gas' or 'power'. The fires it was feeding go out,
        and its fires can no longer be a threat. Returns how many active fires this put
        out. A no-op if the level doesn't have that hazard or it's already off."""
        if self.supplies.get(hazard) != "on":
            return 0
        self.supplies[hazard] = "off"
        cls = HAZARD_CLASS.get(hazard)
        out = [f for f in self.fires if f["class"] == cls]
        if out:
            self.fires = [f for f in self.fires if f["class"] != cls]
            for _ in out:
                self.stats["extinguished"] += 1
                self.budget += EXTINGUISH_REWARD
        # Cutting the last fire mid-level can be the winning move.
        if self.status == "playing" and self.spawned >= len(self.schedule) and not self.fires:
            self.status = "won"
        return len(out)

    def _fire_pos(self, fire: dict) -> tuple:
        return path_point_at(self.level["path"], fire["progress"])

    def _nearest_fire_in_range(self, tower: dict):
        tx, ty = tower["spot"][0], tower["spot"][1]
        best, best_d = None, None
        for f in self.fires:
            px, py = self._fire_pos(f)
            d = ((px - tx) ** 2 + (py - ty) ** 2) ** 0.5
            if d <= TOWER_RANGE and (best_d is None or d < best_d):
                best, best_d = f, d
        return best

    def total_fires(self) -> int:
        return len(self.schedule)

    def recap(self) -> dict:
        """The end-of-level summary (ITEM-013): how many fires were handled correctly,
        how many leaked, how many mistakes, a knowledge score, and each class that
        appeared with its right tool. Framework-free, so it's testable and the browser
        can render it."""
        total = len(self.schedule)
        handled = self.stats["extinguished"]
        knowledge = round(100 * handled / total) if total else 0
        names = {c["id"]: c["name_de"] for c in FIRE_CLASSES}
        icons = {c["id"]: c["icon"] for c in FIRE_CLASSES}
        seen_order = []
        for ev in self.schedule:
            if ev["class"] not in seen_order:
                seen_order.append(ev["class"])
        supplies = self.level.get("supplies", [])
        classes = [
            {"id": cid, "name_de": names.get(cid, cid), "icon": icons.get(cid, "🔥"),
             "right_tool_de": right_action_de(cid, supplies)}
            for cid in seen_order
        ]
        return {
            "status": self.status,
            "total": total,
            "handled": handled,
            "leaked": self.leaked,
            "mistakes": self.stats["danger_hits"] + self.stats["useless_hits"],
            "knowledge": knowledge,
            "classes": classes,
        }

