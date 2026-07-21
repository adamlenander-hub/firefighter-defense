"""Levels (ITEM-007) as data — the map, path, build spots, waves — plus the play
tuning constants and the geometry/level helpers the engine and API read."""
from __future__ import annotations

from config import *
from content import *

# --- Levels (ITEM-007): the map, path, build spots, and building, as data -----
#
# Levels are data, not code — a new level is a new entry here (these can move into
# the database later like the fire content). Coordinates live in each level's own
# virtual space (its width/height); the browser scales them to fit the screen.

LEVELS = [
    {
        # Campaign mission 1 (ITEM-027). Reuses the original first level; Anton's
        # open/anecdote/hint/close framing lives in ANTON["missions"]["fachwerk"].
        "key": "fachwerk",
        "campaign": True,
        "mission": 1,
        "name": "Die Nacht des Fachwerkfeuers",
        "place_de": "Enge Fachwerkgasse in der Königsteiner Altstadt",
        "size": {"w": 960, "h": 540},
        "path": [[20, 150], [320, 150], [320, 350], [640, 350], [640, 160], [880, 160]],
        "build_spots": [[190, 90], [400, 250], [520, 410], [760, 100], [770, 250]],
        # lives=3 (ITEM-015 tuning): a player must handle all three fire types this
        # level teaches. Ignoring the cooking-oil fires (3 of them) — e.g. an
        # all-powder defence, since powder does nothing to a fat fire — leaks 3 fires
        # and loses. Correct play (right tool per class) leaks none and wins with room
        # to spare. Budget stays generous here; the tight budget squeeze is ITEM-017.
        "building": {"x": 900, "y": 160, "lives": 3, "name_de": "Wohnhaus"},
        "budget": 220,
        # Waves of fires (the MVP trio for this level: solids, electrical, cooking oil).
        "waves": [
            {"gap": 1.2, "fires": ["A", "A", "A"]},
            {"gap": 1.1, "fires": ["A", "electrical", "A", "F"]},
            {"gap": 1.0, "fires": ["electrical", "F", "A", "electrical", "F"]},
        ],
    },
    {
        # Campaign mission 3 (ITEM-027). Reuses the existing Kurpark fire level with
        # storm + trapped-visitors framing (ITEM-030: the visitors are what you
        # protect + an optional bonus in Anton's narration; the tower-defense core is
        # UNCHANGED — winning is still only by the safe, correct fire choice).
        "key": "kurpark",
        "campaign": True,
        "mission": 3,
        "name": "Der Kurpark im Sturm",
        "place_de": "Wege durch den Königsteiner Kurpark",
        "size": {"w": 960, "h": 540},
        "path": [[20, 430], [240, 430], [240, 120], [520, 120], [520, 440], [820, 440], [820, 220]],
        "build_spots": [[140, 300], [360, 55], [430, 300], [660, 370], [700, 300]],
        # ITEM-017 balance: lives 3 and enough electrical + cooking-oil fires that no
        # single-tool spam can win — e.g. powder/CO₂ leak the cooking-oil fires, the
        # wet-chemical tool leaks the electrical fires. Only a correct mix wins.
        "building": {"x": 850, "y": 200, "lives": 3, "name_de": "Kurhaus"},
        "budget": 240,
        "waves": [
            {"gap": 1.2, "fires": ["A", "A", "B"]},
            {"gap": 1.1, "fires": ["electrical", "F", "B", "A"]},
            {"gap": 1.0, "fires": ["F", "electrical", "F", "electrical"]},
        ],
    },
    {
        # ITEM-016: the combined level that introduces the remaining fire types —
        # flammable liquids (B), gases (C), and burning metals (D) — plus the two
        # "cut the supply first" lessons. Gas and electrical fires here can ONLY be
        # dealt with by cutting their supply (see "supplies"); spraying them does
        # nothing. Liquids need foam or powder; burning metal needs the special metal
        # powder (everything else is dangerous on metal).
        "key": "schlosserei",
        "campaign": False,   # side / training level — NOT one of the four story missions
        "mission": None,
        "name": "Feuer in der Schlosserei",
        "place_de": "Die alte Schlosserei am Fuß des Königsteiner Burgbergs",
        "size": {"w": 960, "h": 540},
        "path": [[20, 130], [280, 130], [280, 380], [560, 380], [560, 170], [820, 170], [820, 430]],
        "build_spots": [[150, 60], [380, 270], [700, 90], [720, 300], [430, 470]],
        "building": {"x": 880, "y": 430, "lives": 3, "name_de": "Werkstatt"},
        "budget": 320,
        "supplies": ["gas", "power"],
        "waves": [
            {"gap": 1.3, "fires": ["A", "B", "A"]},
            {"gap": 1.2, "fires": ["C", "B", "electrical"]},
            {"gap": 1.1, "fires": ["D", "C", "electrical", "D"]},
        ],
    },
    {
        # Campaign mission 2 (ITEM-027) — NEW. The castle library. SIMPLIFIED (Adam's
        # review): an ELECTRICAL fire (old wiring/lamp) among burning old books/paper
        # (Class A) — no burning-metal fire here anymore (that moved to mission 4).
        #
        # DECISION (Adam): the library must teach "water is dangerous on the electrical
        # fire, and the clean no-mess choice protects the records." Why this needs the
        # cut-the-power step: an ordinary electrical+paper library CANNOT satisfy the
        # "no single tool wins" guard on its own, because ABC powder is 'good' on BOTH
        # electrical and Class A (and CO₂ clears both too), so a one-tool defence would
        # win. Rather than re-add a specialist fire, this level declares supplies:
        # ["power"] (the ITEM-016 mechanic): the live wiring can't be sprayed out at
        # all — you must CUT THE POWER first (the cleanest, no-water, no-residue fix
        # that leaves the priceless records untouched). Only then handle the burning
        # books with an ordinary extinguisher. So winning needs TWO different safe
        # actions, and no single tool can beat the level — the guard holds honestly,
        # and the lesson is the reference's own headline: "cut the power first."
        "key": "bibliothek",
        "campaign": True,
        "mission": 2,
        "name": "Der Brand in der Burgbibliothek",
        "place_de": "Das alte Archiv in der Königsteiner Burg",
        "size": {"w": 960, "h": 540},
        "path": [[20, 120], [260, 120], [260, 360], [540, 360], [540, 170], [820, 170], [820, 430]],
        "build_spots": [[150, 250], [400, 260], [400, 460], [690, 90], [700, 300]],
        "building": {"x": 890, "y": 430, "lives": 3, "name_de": "Archiv"},
        "budget": 200,
        "supplies": ["power"],
        # Correct play: cut the power (handles the electrical fault cleanly, no water on
        # the records) + an ordinary extinguisher (water/foam/powder) on the burning
        # books. Water on the LIVE wiring is wrong (Anton warns: cut the power first).
        "waves": [
            {"gap": 1.3, "fires": ["electrical", "A", "electrical"]},
            {"gap": 1.2, "fires": ["A", "electrical", "A"]},
            {"gap": 1.1, "fires": ["electrical", "A", "electrical"]},
        ],
    },
    {
        # Campaign mission 4 (ITEM-027) — NEW. The anniversary festival stage.
        # Teaches the design brief's classes — flammable liquids (Class B) and
        # electrical near the stage — PLUS the relocated burning-metal fire: a modern
        # lithium power-pack / e-scooter battery among the stage gear is a Class D
        # (metals) fire per the reference (examples include Lithium). Water is dangerous
        # on ALL three, so an all-water defence loses hard. The firework is story
        # dressing only (ANTON["missions"]["feuerwerk"]); there is NO invented
        # "firework" fire class.
        # Correct play: CO₂ on the fuel + wiring (B, electrical) + the metal powder on
        # the battery (D). No single tool clears all three: CO₂/powder leak the battery,
        # metal powder leaks the fuel/wiring, wet chemical/foam are dangerous, water is
        # dangerous everywhere — so the "no single tool wins" guard holds.
        "key": "feuerwerk",
        "campaign": True,
        "mission": 4,
        "name": "Das Jubiläumsfeuerwerk in Gefahr",
        "place_de": "Die Festbühne beim Jubiläumsfest",
        "size": {"w": 960, "h": 540},
        "path": [[20, 200], [220, 200], [220, 430], [500, 430], [500, 150], [760, 150], [760, 400]],
        # ITEM-032: spot 2 was [360,100] = 148.7px from the path, beyond a tower's
        # 130px reach (a tower there hit nothing). Moved to [440,90] = 84.9px out —
        # still ≥46px clear of the road, now comfortably within reach of the bend.
        "build_spots": [[120, 320], [360, 300], [440, 90], [640, 280], [690, 60]],
        "building": {"x": 840, "y": 400, "lives": 3, "name_de": "Festbühne"},
        "budget": 300,
        "waves": [
            {"gap": 1.3, "fires": ["B", "B", "electrical"]},
            {"gap": 1.2, "fires": ["electrical", "D", "B", "D"]},
            {"gap": 1.1, "fires": ["D", "electrical", "D", "electrical"]},
        ],
    },
]

# Wave timing + fire speed (ITEM-008). Kept as named dials so they're easy to tune.
FIRST_SPAWN_DELAY = 1.0      # seconds before the first fire appears
WAVE_PAUSE = 3.0            # seconds of calm between waves
FIRE_PX_PER_SEC = 90.0     # how fast a fire walks the path (pixels per second)

# Tower dials (ITEM-009). The browser mirrors these — keep the two in step.
TOWER_RANGE = 130.0        # how far a tower can reach a fire (pixels)
TOWER_COOLDOWN = 0.7       # seconds between a tower's shots
EXTINGUISH_REWARD = 12     # budget earned for putting a fire out with a correct tool
SMART_BONUS = 6            # extra budget for using the ideal (good) tool
DANGER_SPEEDUP = 0.10      # a dangerous mismatch makes the fire lurch this far toward the building
# A build spot's centre must be at least this far from the path so a placed tower never
# overlaps the road (path half-width ~20 + tower radius ~20, plus a little gap).
BUILD_SPOT_CLEARANCE = 46.0

# --- ITEM-041: fires resist being put out — a tool's hit wears them down rather
# than clearing them in one shot. FIRE_HP is the resistance every fire starts with;
# a hit's damage is subtracted from it and the fire only goes out once it reaches
# zero. The IDEAL ("good") tool still clears a fire in a single hit — unchanged pace,
# so every place-geometry/timing tuning done for earlier items keeps working — while
# the merely ACCEPTABLE ("weak") tool needs two hits, visibly smouldering a moment
# longer in between (drawFire shrinks the flame toward the kill). Useless and
# dangerous tools NEVER remove any hp, at any duration — that invariant is unchanged
# and is guarded by tests.
FIRE_HP = 1.0              # every fire's starting extinguish-resistance
GOOD_HIT_DAMAGE = 1.0      # the ideal tool: one hit clears a fire (kept instant)
WEAK_HIT_DAMAGE = 0.55     # the acceptable tool: needs two hits to fully wear it down

# --- ITEM-040: extinguishers deplete. Each placed tower gets a limited number of
# shots ("charge"); once it fires its last shot it's removed, freeing the spot so the
# player has to notice and re-buy. DECISION: charge is only spent on a shot that
# actually discharges AT the fire — a correct/acceptable hit, or a dangerous
# mismatch that backfires — never on a shot that's completely useless (the tool
# can't touch that class at all, e.g. spraying a fire whose supply hazard is still
# on). This keeps a tower correctly aimed at ITS class of fire from being bankrupted
# by an unrelated fire that merely wanders through its range, while still making a
# genuinely DANGEROUS choice cost exactly as much charge as a right one (the wrong
# tool is never cheaper). Charge tightens across the four campaign missions
# (mission 1 the most generous, mission 4 the tightest); levels outside the
# campaign use the generous baseline.
TOWER_CHARGE_BASE = 8
CAMPAIGN_CHARGE_FACTOR = {1: 1.0, 2: 0.85, 3: 0.7, 4: 0.55}
MIN_TOWER_CHARGE = 3       # floor so no mission can ever make a tower useless on arrival


def tower_charge_for(level: dict) -> int:
    """How many shots a freshly-placed tower gets on this level (ITEM-040)."""
    factor = CAMPAIGN_CHARGE_FACTOR.get(level.get("mission"), 1.0)
    return max(MIN_TOWER_CHARGE, round(TOWER_CHARGE_BASE * factor))


# --- ITEM-034: water on a liquid (B) or cooking-oil (F) fire is dangerous — it can
# throw burning liquid, splitting the fire in two. MAX_ACTIVE_FIRES caps how many
# fires can ever be alive on the path at once, so a chain of splits can never make a
# level unwinnable-by-explosion — beyond the cap, a dangerous hit still lurches the
# fire toward the building (the ITEM-010 reaction) but no longer spawns a second one.
MAX_ACTIVE_FIRES = 14


def build_schedule(level: dict) -> list:
    """Turn a level's waves into a flat, deterministic spawn schedule:
    a list of {"t": seconds, "class": id, "wave": n}, sorted by time. Deterministic
    so it can be tested and so every player in a game sees the same sequence."""
    schedule = []
    t = FIRST_SPAWN_DELAY
    for wave_index, wave in enumerate(level.get("waves", [])):
        gap = wave.get("gap", 1.0)
        for class_id in wave["fires"]:
            schedule.append({"t": round(t, 3), "class": class_id, "wave": wave_index})
            t += gap
        t += WAVE_PAUSE
    return schedule



def level_count() -> int:
    return len(LEVELS)


def get_level(index: int) -> dict | None:
    return LEVELS[index] if 0 <= index < len(LEVELS) else None


def level_by_key(key: str) -> dict | None:
    """Find a level by its stable key (e.g. 'fachwerk', 'bibliothek'). Used so the
    checks and campaign logic don't depend on a level's position in the list."""
    return next((lv for lv in LEVELS if lv.get("key") == key), None)


def campaign_missions() -> list:
    """The story missions in play order (by mission number), each as
    {index, key, name, mission}. The side/training level is excluded."""
    out = [
        {"index": i, "key": lv.get("key"), "name": lv["name"], "mission": lv.get("mission")}
        for i, lv in enumerate(LEVELS)
        if lv.get("campaign") and lv.get("mission")
    ]
    out.sort(key=lambda m: m["mission"])
    return out


def _path_length(waypoints: list) -> float:
    total = 0.0
    for (x1, y1), (x2, y2) in zip(waypoints, waypoints[1:]):
        total += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    return total


def path_point_at(waypoints: list, t: float) -> tuple:
    """Point (x, y) a fraction t (0..1) along the path. t<=0 is the start, t>=1 the
    end. This is how things travel the path — a preview marker now, fires later."""
    if not waypoints:
        return (0.0, 0.0)
    if t <= 0:
        return (float(waypoints[0][0]), float(waypoints[0][1]))
    if t >= 1:
        return (float(waypoints[-1][0]), float(waypoints[-1][1]))
    total = _path_length(waypoints)
    if total == 0:
        return (float(waypoints[0][0]), float(waypoints[0][1]))
    target = t * total
    walked = 0.0
    for (x1, y1), (x2, y2) in zip(waypoints, waypoints[1:]):
        seg = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if seg and walked + seg >= target:
            f = (target - walked) / seg
            return (x1 + (x2 - x1) * f, y1 + (y2 - y1) * f)
        walked += seg
    return (float(waypoints[-1][0]), float(waypoints[-1][1]))


def level_json(index: int) -> dict | None:
    """A level's data ready to hand to the browser. Framework-free, so testable
    without a server."""
    lv = get_level(index)
    if lv is None:
        return None
    return {
        "index": index,
        "name": lv["name"],
        "place_de": lv["place_de"],
        "size": lv["size"],
        "path": lv["path"],
        "build_spots": lv["build_spots"],
        "building": lv["building"],
        "budget": lv.get("budget", 0),
        # Which supplies (gas/power) this level lets you cut off (ITEM-016).
        "supplies": lv.get("supplies", []),
        # The spawn schedule is computed on the server and sent, so the browser
        # doesn't re-derive it (keeps one source of truth — a retro learning).
        "schedule": build_schedule(lv),
        "waves": lv.get("waves", []),
        # Campaign metadata (ITEM-027) + Anton's per-mission framing (ITEM-026/027).
        "key": lv.get("key"),
        "campaign": bool(lv.get("campaign")),
        "mission": lv.get("mission"),
        "anton": mission_lines_de(lv.get("key", "")),
        # The reward vignette that plays when this mission is won (ITEM-028).
        "vignette": vignette_de(lv.get("key", "")),
    }


def levels_index() -> list:
    """The level list for the switcher, with campaign metadata so the browser can
    show the four story missions in order (and gate them) and keep the training
    level as a free-choice side level (ITEM-027)."""
    return [
        {"index": i, "name": lv["name"], "key": lv.get("key"),
         "campaign": bool(lv.get("campaign")), "mission": lv.get("mission")}
        for i, lv in enumerate(LEVELS)
    ]


def _point_segment_distance(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def point_to_path_distance(x, y, waypoints) -> float:
    """Shortest distance from a point to the path (the nearest of its segments)."""
    best = None
    for (ax, ay), (bx, by) in zip(waypoints, waypoints[1:]):
        d = _point_segment_distance(x, y, ax, ay, bx, by)
        best = d if best is None else min(best, d)
    return best if best is not None else float("inf")

