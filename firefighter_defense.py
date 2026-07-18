"""
Firefighter Defense — Königstein 150-year anniversary edition ("Anton der Burggeist").

A single self-contained Python web app that
  * serves one page confirming the game is running (ITEM-005),
  * creates its own SQLite database next to itself on first run (ITEM-005), and
  * loads the fire facts — classes, tools, and the right/useless/dangerous matrix —
    from the source of truth below into that database, with a check that guards them
    against the fire-safety reference (ITEM-006).

It does NOT yet contain the levels or the playable game — those are later backlog
items. The shape every later item relies on: one FastAPI app, SQLite built on
startup from a source of truth, everything configurable by environment variable,
nothing tied to one specific computer, deployable unchanged.

Run it:
    pip install -r requirements.txt
    python3 firefighter_defense.py
Then open the address it prints (default http://localhost:3000).

Check the fire facts are correct (no server needed):
    python3 firefighter_defense.py --check-content

Check the first level is only won by safe, correct play (no server needed):
    python3 firefighter_defense.py --simulate

Configuration (all optional, read from the environment):
    HOST           network address to bind      (default 0.0.0.0 = reachable on the LAN)
    PORT           port to serve on             (default 3000; hosting providers set this)
    DATABASE_PATH  where the SQLite file lives   (default: next to this script)
"""

from __future__ import annotations  # lets the newer "str | None" hints work on Python 3.9+

import os
import sqlite3
from contextlib import asynccontextmanager, closing

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

# --- Configuration, all overridable by environment variable -------------------

HERE = os.path.dirname(os.path.abspath(__file__))

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "3000"))
# Default the database next to this script. No machine-specific paths are baked in,
# so the same code runs on a laptop or on a hosting server unchanged.
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(HERE, "firefighter_defense.db"))

# Bumped whenever the built-in content changes, so a later item (ITEM-006/039-style)
# can rebuild the database from the source of truth when this number moves.
SCHEMA_VERSION = 1

# Bumped whenever the fire content below changes, so the database rebuilds itself
# from this source on the next start (ITEM-006 / the "content version stamp" idea).
CONTENT_VERSION = 1

APP_TITLE = "Firefighter Defense — Königstein"


# --- The fire facts: the machine-readable encoding of FIRE_SAFETY_REFERENCE.md --
#
# This is the single source of truth the game reads. It mirrors docs/
# FIRE_SAFETY_REFERENCE.md (the human-readable reference); the two MUST stay in
# step — if you change a fact, change it in both and bump CONTENT_VERSION. The
# content check (check_content) enforces the safety-critical facts so a wrong edit
# can't slip through silently.

# The four possible outcomes when a tool meets a fire.
OUTCOMES = ("good", "weak", "useless", "danger")

# Fire classes (European / EN scheme, decided in ITEM-001), in teaching order.
# Each class carries an icon AND a colour AND a letter, so it's tellable apart by
# more than colour alone (colour-blind / greyscale safe — ITEM-008 requirement).
FIRE_CLASSES = [
    {"id": "A", "name_de": "Brandklasse A", "name_en": "solids",
     "examples_de": "Holz, Papier, Textilien, Fachwerk", "icon": "🪵",
     "colour": "#a16207", "note_de": None},
    {"id": "B", "name_de": "Brandklasse B", "name_en": "liquids",
     "examples_de": "Benzin, Öl, Farbe, Spiritus", "icon": "🛢️",
     "colour": "#7c3aed", "note_de": None},
    {"id": "C", "name_de": "Brandklasse C", "name_en": "gases",
     "examples_de": "Propan, Butan, Erdgas", "icon": "💨",
     "colour": "#0d9488", "note_de": "Zuerst die Gaszufuhr absperren."},
    {"id": "electrical", "name_de": "Elektrobrand", "name_en": "electrical",
     "examples_de": "Verteiler, Ladegeräte, Geräte unter Spannung", "icon": "⚡",
     "colour": "#2563eb", "note_de": "Wenn möglich zuerst den Strom abschalten."},
    {"id": "D", "name_de": "Brandklasse D", "name_en": "metals",
     "examples_de": "Magnesium, Aluminium, Lithium", "icon": "🔩",
     "colour": "#64748b", "note_de": None},
    {"id": "F", "name_de": "Brandklasse F", "name_en": "cooking oil",
     "examples_de": "Fritteuse, Fettbrand", "icon": "🍳",
     "colour": "#db2777", "note_de": None},
]


def classes_display() -> list:
    """Display info per fire class for the browser (id, name, icon, colour, letter).
    Framework-free so it can be tested and served without a server."""
    letters = {"A": "A", "B": "B", "C": "C", "electrical": "E", "D": "D", "F": "F"}
    return [
        {"id": c["id"], "name_de": c["name_de"], "icon": c["icon"],
         "colour": c["colour"], "letter": letters.get(c["id"], c["id"][:1].upper()),
         "card_de": CLASS_CARDS.get(c["id"], ""), "right_tool_de": right_tool_de(c["id"])}
        for c in FIRE_CLASSES
    ]

# Extinguisher tools (the towers). Fire blanket is a special item added later.
# "cost" is what it takes to place one (ITEM-009); "short" + "hex" are for drawing
# the tower and the tool palette.
TOOLS = [
    {"id": "water", "name_de": "Wasser", "name_en": "water", "colour_de": "Rot", "cost": 40, "short": "H₂O", "hex": "#0284c7"},
    {"id": "foam", "name_de": "Schaum", "name_en": "foam", "colour_de": "Creme", "cost": 60, "short": "Schaum", "hex": "#d97706"},
    {"id": "co2", "name_de": "Kohlendioxid (CO₂)", "name_en": "CO2", "colour_de": "Schwarz", "cost": 80, "short": "CO₂", "hex": "#1f2937"},
    {"id": "powder", "name_de": "Pulver (ABC)", "name_en": "dry powder", "colour_de": "Blau", "cost": 70, "short": "Pulver", "hex": "#4d7c0f"},
    {"id": "wetchem", "name_de": "Fettbrandlöscher", "name_en": "wet chemical", "colour_de": "Gelb", "cost": 80, "short": "Fett", "hex": "#be123c"},
    {"id": "metal", "name_de": "Metallbrandpulver", "name_en": "metal powder", "colour_de": "—", "cost": 120, "short": "Metall", "hex": "#57534e"},
]


def tools_display() -> list:
    """Tool info for the browser (palette + drawing towers): id, name, cost, short
    label, colour. Framework-free."""
    return [
        {"id": t["id"], "name_de": t["name_de"], "cost": t["cost"],
         "short": t["short"], "hex": t["hex"]}
        for t in TOOLS
    ]


def tool_cost(tool_id: str) -> int:
    for t in TOOLS:
        if t["id"] == tool_id:
            return t["cost"]
    return 0

# The matrix: for each fire class, the outcome of each tool. Values from
# FIRE_SAFETY_REFERENCE.md section 3.
MATRIX = {
    "A":          {"water": "good",   "foam": "good",   "co2": "weak",    "powder": "good",   "wetchem": "good",    "metal": "useless"},
    "B":          {"water": "danger", "foam": "good",   "co2": "good",    "powder": "good",   "wetchem": "weak",    "metal": "useless"},
    "C":          {"water": "useless","foam": "useless","co2": "useless", "powder": "good",   "wetchem": "useless", "metal": "useless"},
    "electrical": {"water": "danger", "foam": "danger", "co2": "good",    "powder": "good",   "wetchem": "danger",  "metal": "useless"},
    "D":          {"water": "danger", "foam": "danger", "co2": "useless", "powder": "danger", "wetchem": "danger",  "metal": "good"},
    "F":          {"water": "danger", "foam": "danger", "co2": "danger",  "powder": "useless","wetchem": "good",    "metal": "useless"},
}

# Short German reasons for the dangerous pairings (the headline lessons). Used for
# the teaching feedback later (ITEM-012) and to make check failures readable.
DANGER_REASONS = {
    ("F", "water"): "Wasser im Fettbrand führt zur Fettexplosion (Stichflamme).",
    ("electrical", "water"): "Wasser leitet Strom – Stromschlaggefahr.",
    ("electrical", "foam"): "Schaum leitet Strom – nicht auf Spannung.",
    ("electrical", "wetchem"): "Fettbrandlöscher leitet Strom – nicht auf Elektrobrand.",
    ("D", "water"): "Wasser auf brennendem Metall reagiert heftig.",
    ("D", "foam"): "Wasserbasiertes Mittel auf Metall reagiert heftig.",
    ("D", "wetchem"): "Wasserbasiertes Mittel auf Metall reagiert heftig.",
    ("B", "water"): "Wasser verteilt die brennende Flüssigkeit.",
    ("F", "foam"): "Wasserbasiertes Mittel im Fettbrand – Stichflammengefahr.",
    ("F", "co2"): "CO₂ kann brennendes Fett wegschleudern.",
}

# Safety-critical facts the check hard-asserts, so a wrong edit to any of these
# squares makes the check fail (not just teach the wrong thing). Drawn from the
# reference's "notes that must survive."
CRITICAL_FACTS = [
    ("F", "water", "danger"),
    ("electrical", "water", "danger"),
    ("F", "wetchem", "good"),
    ("electrical", "co2", "good"),
    ("D", "metal", "good"),
    ("D", "water", "danger"),
    ("C", "powder", "good"),
]

# Anton's short "meet the fire" explanations (ITEM-011), in his warm, encouraging
# voice. Shown the first time each class appears. Facts stay true to the reference.
CLASS_CARDS = {
    "A": "Holz, Papier, Stoff — ein ganz gewöhnliches Feuer. Wasser, Schaum oder Pulver löschen es sicher.",
    "B": "Brennende Flüssigkeit! Kein Wasser, das spritzt nur. Schaum, Pulver oder CO₂ ersticken die Flammen.",
    "C": "Brennendes Gas. Wenn möglich zuerst die Gaszufuhr absperren! Pulver hält die Flamme in Schach.",
    "electrical": "Da steht etwas unter Strom. Bloß kein Wasser — Stromschlag! Am besten CO₂ (und den Strom abschalten).",
    "D": "Brennendes Metall — heikel. Nur das Spezial-Metallbrandpulver hilft. Wasser wäre gefährlich.",
    "F": "Fett in der Fritteuse brennt. NIE Wasser — das gibt eine Stichflamme! Der Fettbrandlöscher hilft.",
}


# --- Supply-hazard mechanic (ITEM-016) ---------------------------------------
# Some fires can't just be sprayed — the supply feeding them must be cut off first.
# A level opts in via "supplies": ["gas", "power"]. In such a level, spraying that
# kind of fire while its supply is on does nothing (Anton says cut the supply first);
# cutting the supply puts those fires out. Level 1 declares no supplies, so it keeps
# its original "use the right extinguisher" behaviour for electrical fires.
HAZARD_CLASS = {"gas": "C", "power": "electrical"}
HAZARD_ACTION_DE = {"gas": "Gaszufuhr absperren", "power": "Strom abschalten"}
HAZARD_BUTTON_DE = {"gas": "🔧 Gas absperren", "power": "⚡ Strom abschalten"}
HAZARD_WARN_DE = {
    "gas": "Bei Gasbränden zuerst die Gaszufuhr absperren!",
    "power": "Bei Elektrobränden zuerst den Strom abschalten!",
}


def right_tool_de(class_id: str) -> str:
    """The name of a correct (good) tool for a class, for suggestions. '' if none."""
    row = MATRIX.get(class_id, {})
    for t in TOOLS:
        if row.get(t["id"]) == "good":
            return t["name_de"]
    return ""


def right_action_de(class_id: str, supplies=None) -> str:
    """The correct action for a class, given a level's supply hazards. If the class
    is fed by a cut-able supply in this level (gas/power), the right action is cutting
    that supply; otherwise it's the right extinguisher."""
    for hazard in (supplies or []):
        if HAZARD_CLASS.get(hazard) == class_id:
            return HAZARD_ACTION_DE[hazard]
    return right_tool_de(class_id)


def feedback_reason(class_id: str, tool_id: str) -> str | None:
    """A short, kind, Anton-voice message for a wrong shot (ITEM-012), or None when
    the tool is fine. Dangerous shots explain the danger; useless shots nudge toward
    the right tool. Facts from the reference."""
    outcome = MATRIX.get(class_id, {}).get(tool_id)
    right = right_tool_de(class_id)
    if outcome == "danger":
        why = DANGER_REASONS.get((class_id, tool_id), "Das macht es nur schlimmer!")
        return why + (f" Nimm lieber {right}." if right else "")
    if outcome == "useless":
        return f"Das wirkt hier leider nicht. Nimm {right}." if right else "Das wirkt hier leider nicht."
    return None


# --- Database ----------------------------------------------------------------

def init_db(database_path: str = DATABASE_PATH) -> None:
    """Create the database file and its base table if they aren't there yet.

    Safe to call every start-up: it only creates what's missing, so a restart
    never loses or duplicates anything. Later items add the real game tables and
    fill them from the fire-safety reference and the story.
    """
    # Make sure the folder exists (it always will for the default, but a custom
    # DATABASE_PATH might point somewhere new).
    parent = os.path.dirname(os.path.abspath(database_path))
    os.makedirs(parent, exist_ok=True)

    with closing(sqlite3.connect(database_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        # Record the schema version so a future rebuild step can notice a change.
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()

    # Build (or rebuild) the fire content from the source of truth (ITEM-006).
    build_content(database_path)


def read_meta(key: str, database_path: str = DATABASE_PATH) -> str | None:
    """Read one value from the meta table. Returns None if the database or the
    table isn't there yet, so a page render can never crash just because the
    database hasn't been built — it degrades gracefully instead."""
    try:
        with closing(sqlite3.connect(database_path)) as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else None
    except sqlite3.OperationalError:
        # e.g. the table doesn't exist yet — treat as "not set" rather than error.
        return None


# --- The fire content in the database (ITEM-006) ------------------------------

def build_content(database_path: str = DATABASE_PATH) -> None:
    """Create the fire-content tables and fill them from the source of truth above.
    Rebuilds them whenever CONTENT_VERSION changes, so editing the facts and bumping
    the version updates what the game uses on the next start. Safe to call every
    start-up."""
    parent = os.path.dirname(os.path.abspath(database_path))
    os.makedirs(parent, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fire_classes (
                id TEXT PRIMARY KEY, name_de TEXT, name_en TEXT,
                examples_de TEXT, icon TEXT, note_de TEXT, sort INTEGER
            );
            CREATE TABLE IF NOT EXISTS tools (
                id TEXT PRIMARY KEY, name_de TEXT, name_en TEXT,
                colour_de TEXT, sort INTEGER
            );
            CREATE TABLE IF NOT EXISTS matrix (
                class_id TEXT, tool_id TEXT, outcome TEXT, reason_de TEXT,
                PRIMARY KEY (class_id, tool_id)
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            );
            """
        )
        stored = conn.execute(
            "SELECT value FROM meta WHERE key = 'content_version'"
        ).fetchone()
        if stored and stored[0] == str(CONTENT_VERSION):
            return  # already current; nothing to rebuild

        # Rebuild from scratch so a change to the facts is reflected exactly.
        conn.execute("DELETE FROM fire_classes")
        conn.execute("DELETE FROM tools")
        conn.execute("DELETE FROM matrix")
        for i, c in enumerate(FIRE_CLASSES):
            conn.execute(
                "INSERT INTO fire_classes (id,name_de,name_en,examples_de,icon,note_de,sort) "
                "VALUES (?,?,?,?,?,?,?)",
                (c["id"], c["name_de"], c["name_en"], c["examples_de"], c["icon"], c["note_de"], i),
            )
        for i, t in enumerate(TOOLS):
            conn.execute(
                "INSERT INTO tools (id,name_de,name_en,colour_de,sort) VALUES (?,?,?,?,?)",
                (t["id"], t["name_de"], t["name_en"], t["colour_de"], i),
            )
        for class_id, row in MATRIX.items():
            for tool_id, outcome in row.items():
                conn.execute(
                    "INSERT INTO matrix (class_id,tool_id,outcome,reason_de) VALUES (?,?,?,?)",
                    (class_id, tool_id, outcome, DANGER_REASONS.get((class_id, tool_id))),
                )
        conn.execute(
            "INSERT INTO meta (key,value) VALUES ('content_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(CONTENT_VERSION),),
        )
        conn.commit()


def load_matrix(database_path: str = DATABASE_PATH) -> dict:
    """Return the stored matrix as {(class_id, tool_id): outcome}."""
    with closing(sqlite3.connect(database_path)) as conn:
        rows = conn.execute("SELECT class_id, tool_id, outcome FROM matrix").fetchall()
    return {(r[0], r[1]): r[2] for r in rows}


def content_counts(database_path: str = DATABASE_PATH) -> tuple[int, int]:
    """(number of fire classes, number of tools) currently stored, or (0, 0) if the
    content isn't built yet — never raises, so the page can't crash."""
    try:
        with closing(sqlite3.connect(database_path)) as conn:
            nc = conn.execute("SELECT COUNT(*) FROM fire_classes").fetchone()[0]
            nt = conn.execute("SELECT COUNT(*) FROM tools").fetchone()[0]
            return nc, nt
    except sqlite3.OperationalError:
        return 0, 0


def check_content(database_path: str = DATABASE_PATH) -> tuple[bool, list]:
    """Confirm the fire facts the game will use are correct and complete.

    Builds the content first, then checks it against the source of truth AND a set
    of safety-critical facts, so a wrong edit can't slip through silently. Returns
    (ok, problems) where problems is a list of plain-language strings.
    Framework-free, so it runs anywhere including CI."""
    build_content(database_path)
    problems: list[str] = []

    db = load_matrix(database_path)
    class_ids = [c["id"] for c in FIRE_CLASSES]
    tool_ids = [t["id"] for t in TOOLS]

    # 1. Completeness — every class × tool cell exists.
    for cid in class_ids:
        for tid in tool_ids:
            if (cid, tid) not in db:
                problems.append(f"Missing matrix cell: {cid} × {tid}.")

    # 2. Every stored outcome is one of the allowed values.
    for (cid, tid), outcome in db.items():
        if outcome not in OUTCOMES:
            problems.append(f"Invalid outcome '{outcome}' for {cid} × {tid}.")

    # 3. Stored data matches the source of truth exactly (catches database drift).
    for cid in class_ids:
        for tid in tool_ids:
            expected = MATRIX.get(cid, {}).get(tid)
            actual = db.get((cid, tid))
            if expected is not None and actual is not None and actual != expected:
                problems.append(
                    f"Stored {cid} × {tid} is '{actual}' but the reference says '{expected}'."
                )

    # 4. Every fire class must have at least one correct (good) tool.
    for cid in class_ids:
        if not any(db.get((cid, tid)) == "good" for tid in tool_ids):
            problems.append(f"Fire class {cid} has no correct tool — nothing puts it out.")

    # 5. Safety-critical facts must hold exactly (the headline 'never do this' lessons).
    for cid, tid, must_be in CRITICAL_FACTS:
        actual = db.get((cid, tid))
        if actual != must_be:
            problems.append(
                f"SAFETY FACT WRONG: {cid} × {tid} must be '{must_be}' but is '{actual}'."
            )

    return (len(problems) == 0, problems)


# --- Levels (ITEM-007): the map, path, build spots, and building, as data -----
#
# Levels are data, not code — a new level is a new entry here (these can move into
# the database later like the fire content). Coordinates live in each level's own
# virtual space (its width/height); the browser scales them to fit the screen.

LEVELS = [
    {
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
        "name": "Der Kurpark im Sturm",
        "place_de": "Wege durch den Königsteiner Kurpark",
        "size": {"w": 960, "h": 540},
        "path": [[20, 430], [240, 430], [240, 120], [520, 120], [520, 440], [820, 440], [820, 220]],
        "build_spots": [[140, 300], [360, 55], [430, 300], [660, 370], [700, 300]],
        "building": {"x": 850, "y": 200, "lives": 4, "name_de": "Kurhaus"},
        "budget": 200,
        "waves": [
            {"gap": 1.2, "fires": ["A", "A", "B"]},
            {"gap": 1.0, "fires": ["B", "electrical", "A", "F"]},
        ],
    },
    {
        # ITEM-016: the combined level that introduces the remaining fire types —
        # flammable liquids (B), gases (C), and burning metals (D) — plus the two
        # "cut the supply first" lessons. Gas and electrical fires here can ONLY be
        # dealt with by cutting their supply (see "supplies"); spraying them does
        # nothing. Liquids need foam or powder; burning metal needs the special metal
        # powder (everything else is dangerous on metal).
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
            self.fires.append({"id": self._next_id, "class": cls, "progress": 0.0})
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
                # the supply first (the browser shows Anton's warning).
                target["reaction"] = "useless"
                self.stats["useless_hits"] += 1
                continue
            outcome = self.matrix.get((target["class"], tw["tool"]))
            if outcome in ("good", "weak"):
                # Correct (or acceptable) tool: fire goes out, budget earned back;
                # the ideal ("good") tool earns a small smart-play bonus on top.
                self.fires = [f for f in self.fires if f["id"] != target["id"]]
                self.budget += EXTINGUISH_REWARD + (SMART_BONUS if outcome == "good" else 0)
                self.stats["extinguished"] += 1
            elif outcome == "danger":
                # Dangerous mismatch (e.g. water on electrical or on cooking oil):
                # it backfires — the fire flares and lurches toward the building. No
                # budget. This is the strongest teaching moment.
                target["progress"] = min(0.999, target["progress"] + DANGER_SPEEDUP)
                target["reaction"] = "danger"
                self.stats["danger_hits"] += 1
            else:
                # Useless tool: nothing happens, the shot is wasted, no budget.
                target["reaction"] = "useless"
                self.stats["useless_hits"] += 1
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
        self.towers.append({
            "id": self._next_tower_id, "spot_index": spot_index,
            "spot": spots[spot_index], "tool": tool_id, "cooldown": 0.0,
        })
        self._next_tower_id += 1
        return (True, "ok")

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


def level_count() -> int:
    return len(LEVELS)


def get_level(index: int) -> dict | None:
    return LEVELS[index] if 0 <= index < len(LEVELS) else None


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
    }


def levels_index() -> list:
    return [{"index": i, "name": lv["name"]} for i, lv in enumerate(LEVELS)]


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


def check_levels() -> tuple[bool, list]:
    """Confirm every build spot sits clear of the path, so a placed tower never
    overlaps the road. Returns (ok, problems)."""
    problems: list[str] = []
    for i, lv in enumerate(LEVELS):
        for j, (x, y) in enumerate(lv.get("build_spots", [])):
            d = point_to_path_distance(x, y, lv["path"])
            if d < BUILD_SPOT_CLEARANCE:
                problems.append(
                    f"Level {i + 1} ('{lv['name']}') build spot {j} at ({x},{y}) is only "
                    f"{d:.0f}px from the path (need >= {BUILD_SPOT_CLEARANCE:.0f}) — it overlaps the road."
                )
    return (len(problems) == 0, problems)


# --- Behaviour check: only safe, correct play wins the first level ------------
# This is the "does the game still teach?" guard. It plays the real first level to
# the end with a few strategies and confirms the intended outcomes hold. It's run by
# the `--simulate` command, by the pre-save hook, and by CI — so a change that makes
# the level winnable the wrong way (e.g. by ignoring the cooking-oil fires) is caught.

def _play_out(level: dict, placements: list, cut=(), dt: float = 1 / 30.0) -> dict:
    """Play a level to the end with a player who buys the given towers (spot, tool)
    as soon as the budget allows, optionally cutting supplies (gas/power) at the
    start, then reports the recap. Deterministic."""
    st = GameState(level)
    st.status = "playing"
    for hazard in cut:
        st.shut_off(hazard)
    queue = list(placements)
    t = 0.0
    while st.status == "playing" and t < 180:
        while queue and st.place_tower(queue[0][0], queue[0][1])[0]:
            queue.pop(0)
        st.advance(dt)
        t += dt
    return st.recap()


def behaviour_check() -> tuple[bool, list]:
    """Confirm the first level only rewards safe, correct play. Returns (ok, problems)."""
    problems: list[str] = []
    lv = LEVELS[0]

    # 1. Right tool for every class → a clean win (powder for solids + electrical,
    #    the wet-chemical tool for the cooking-oil fires).
    r = _play_out(lv, [(0, "powder"), (2, "wetchem")])
    if r["status"] != "won" or r["leaked"] != 0:
        problems.append(
            f"Correct play should win the first level with nothing getting through, "
            f"but got status={r['status']}, {r['leaked']} fire(s) leaked."
        )

    # 2. Doing nothing → a loss.
    if _play_out(lv, [])["status"] != "lost":
        problems.append("Placing no towers should lose the first level, but it didn't.")

    # 3. All-water → a loss (water is dangerous on electrical and on cooking oil).
    n = len(lv.get("build_spots", []))
    if _play_out(lv, [(i, "water") for i in range(n)])["status"] != "lost":
        problems.append("An all-water defence should lose the first level, but it didn't.")

    # 4. Ignoring the cooking-oil fires → a loss. An all-powder defence puts out the
    #    solids and electrical fires but does nothing to the cooking-oil (F) fires,
    #    so they must leak and lose the level — the level's core lesson.
    r = _play_out(lv, [(i, "powder") for i in range(n)])
    if r["status"] != "lost":
        problems.append(
            "Ignoring the cooking-oil fires (an all-powder defence) should lose the "
            f"first level, but got status={r['status']} — the fat-fire lesson can be skipped."
        )

    # --- The combined level with the shut-off mechanic (ITEM-016), if present ---
    lv2 = next((l for l in LEVELS if l.get("supplies")), None)
    if lv2 is not None:
        # Correct play: cut the gas and the power, foam the liquids/ordinary fires,
        # metal powder for the burning metal → a clean win with nothing leaking.
        r = _play_out(lv2, [(1, "foam"), (4, "metal")], cut=("gas", "power"))
        if r["status"] != "won" or r["leaked"] != 0:
            problems.append(
                "On the combined level, cutting both supplies and using foam + metal "
                f"powder should win with nothing leaking, but got status={r['status']}, "
                f"{r['leaked']} leaked."
            )
        # Forgetting to cut the supplies → the gas and electrical fires leak → a loss.
        r = _play_out(lv2, [(1, "foam"), (4, "metal")], cut=())
        if r["status"] != "lost":
            problems.append(
                "On the combined level, never cutting the gas/power should lose (those "
                f"fires can't be sprayed out), but got status={r['status']}."
            )
        # All-water, even with the supplies cut → still a loss (water is dangerous on
        # liquids and on burning metal).
        r = _play_out(lv2, [(i, "water") for i in range(5)], cut=("gas", "power"))
        if r["status"] != "lost":
            problems.append("On the combined level, an all-water defence should lose, but it didn't.")

    return (len(problems) == 0, problems)


# --- Page + health content (framework-free, so it can be tested on its own) ----

def health_payload() -> dict:
    """The data behind /health — kept separate from the web layer so it can be
    checked without starting a server."""
    nc, nt = content_counts()
    return {
        "status": "ok",
        "schema_version": read_meta("schema_version"),
        "content_version": read_meta("content_version"),
        "fire_classes": nc,
        "tools": nt,
        "database": os.path.basename(DATABASE_PATH),
    }


def render_game_html() -> str:
    """The game view — a canvas that draws the current level (path, build spots,
    building, lives) with a marker travelling the path to the building. German
    (ITEM-001), plain canvas + JavaScript inside the one app (ITEM-003). A plain
    string (no server needed to check it)."""
    return GAME_HTML


# The whole game view as one HTML string. Plain string (not an f-string) so the
# JavaScript's own { } braces are literal. Level data is fetched from the API, so
# nothing needs to be injected here.
GAME_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Firefighter Defense — Königstein</title>
  <style>
    :root { color-scheme: light dark; }
    * { box-sizing: border-box; }
    body {
      margin: 0; padding: 1rem; min-height: 100vh;
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      background: #fff7ed; color: #7c2d12;
      display: flex; flex-direction: column; align-items: center; gap: .6rem;
    }
    header { text-align: center; }
    h1 { margin: 0; font-size: 1.35rem; }
    .place { margin: .15rem 0 0; color: #9a6a4f; font-size: .9rem; }
    .bar { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; justify-content: center; }
    .lives { font-size: 1.1rem; }
    button {
      font: inherit; padding: .35rem .8rem; border-radius: 999px; cursor: pointer;
      border: 1px solid #e7c9b3; background: #fff; color: #7c2d12;
    }
    button.active { background: #ea580c; color: #fff; border-color: #ea580c; }
    .wrap { width: 100%; max-width: 960px; }
    canvas { width: 100%; height: auto; border-radius: 16px; box-shadow: 0 10px 30px rgba(124,45,18,.12); background:#f4ead8; display:block; }
    .legend { display:flex; flex-wrap:wrap; gap:1rem; justify-content:center; color:#9a6a4f; font-size:.82rem; }
    .legend span::before { content:"● "; }
    .foot { color:#9a6a4f; font-size:.8rem; }
  </style>
</head>
<body>
  <header>
    <h1>Firefighter Defense — Königstein</h1>
    <p style="margin:.1rem 0; font-size:.85rem; color:#b45309; font-weight:600;">🚒 Freiwillige Feuerwehr Königstein im Taunus · 150 Jahre</p>
    <p class="place" id="place">Einsatz wird geladen …</p>
  </header>

  <div class="bar" id="levelBar"></div>
  <div class="bar">
    <span class="lives" id="lives"></span>
    <span id="budget" style="font-weight:600;"></span>
    <button id="startBtn">Einsatz starten</button>
    <label style="font-size:.85rem; color:#9a6a4f;"><input type="checkbox" id="cardsToggle" checked> Antons Karten</label>
    <button id="libBtn">Antons Wissen</button>
    <span id="info" style="color:#9a6a4f; font-size:.9rem;"></span>
  </div>

  <div class="bar" id="toolPalette"></div>
  <div class="bar" id="hazardControls"></div>
  <p class="foot" id="hint">Löscher wählen, dann auf einen blauen Bauplatz tippen. Der richtige Löscher löscht, der falsche wirkt nicht — ein gefährlicher lässt das Feuer auflodern.</p>
  <p id="feedback" style="min-height:1.3em; font-weight:600; text-align:center; margin:.2rem 0;"></p>

  <div class="wrap"><canvas id="board" width="960" height="540"></canvas></div>

  <div class="legend" id="classLegend"></div>
  <div class="legend">
    <span style="color:#c2410c">Start</span>
    <span style="color:#a8a29e">Weg zum Gebäude</span>
    <span style="color:#0369a1">Bauplatz für Löscher</span>
    <span style="color:#15803d">Gebäude</span>
  </div>
  <p class="foot" id="foot">&nbsp;</p>

  <!-- Anton's "meet the fire" card (ITEM-011) -->
  <div id="card" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,.45); align-items:center; justify-content:center; z-index:10;">
    <div style="background:#fff; color:#7c2d12; max-width:26rem; margin:1rem; padding:1.4rem 1.6rem; border-radius:18px; text-align:center; box-shadow:0 20px 50px rgba(0,0,0,.35);">
      <div id="cardIcon" style="font-size:2.6rem;"></div>
      <h3 id="cardTitle" style="margin:.3rem 0;"></h3>
      <p id="cardText" style="line-height:1.5;"></p>
      <p style="font-size:.8rem; color:#9a6a4f; margin:.6rem 0;">— Anton, der Burggeist 👻</p>
      <button id="cardOk">Verstanden</button>
    </div>
  </div>

  <!-- End-of-level recap (ITEM-013) -->
  <div id="recap" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,.5); align-items:center; justify-content:center; z-index:11;">
    <div style="background:#fff; color:#7c2d12; max-width:30rem; margin:1rem; padding:1.4rem 1.6rem; border-radius:18px; box-shadow:0 20px 50px rgba(0,0,0,.35);">
      <h2 id="recapTitle" style="margin:.2rem 0; text-align:center;"></h2>
      <p id="recapScore" style="text-align:center; font-size:1.15rem; font-weight:600; margin:.3rem 0;"></p>
      <p id="recapLine" style="text-align:center; color:#9a6a4f; margin:.2rem 0 .8rem;"></p>
      <div id="recapClasses" style="font-size:.9rem;"></div>
      <div style="text-align:center; margin-top:1rem; display:flex; gap:.5rem; justify-content:center;">
        <button id="recapAgain">Neu starten</button>
        <button id="recapLib">Antons Wissen</button>
      </div>
    </div>
  </div>

  <!-- Antons Wissen library (ITEM-014) -->
  <div id="lib" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,.5); align-items:center; justify-content:center; z-index:12;">
    <div style="background:#fff; color:#7c2d12; max-width:34rem; max-height:86vh; overflow:auto; margin:1rem; padding:1.2rem 1.4rem; border-radius:18px; box-shadow:0 20px 50px rgba(0,0,0,.35);">
      <h2 style="margin:.2rem 0; text-align:center;">Antons Wissen 👻</h2>
      <p style="text-align:center; color:#9a6a4f; margin:.2rem 0 .8rem;">Welcher Löscher passt zu welchem Feuer?</p>
      <div id="libBody" style="font-size:.9rem;"></div>
      <div style="text-align:center; margin-top:1rem;"><button id="libClose">Schließen</button></div>
    </div>
  </div>

  <script>
    // Dials — MUST match the server (GameState). The spawn schedule itself is sent
    // by the server (level.schedule), so it isn't rebuilt here.
    var FIRE_PX_PER_SEC = 90.0;
    var TOWER_RANGE = 130.0, TOWER_COOLDOWN = 0.7, EXTINGUISH_REWARD = 12;
    var SMART_BONUS = 6, DANGER_SPEEDUP = 0.10;
    // Supply-hazard mechanic (ITEM-016), mirroring the server. Kept in step with the
    // Python HAZARD_* constants.
    var HAZARD_CLASS = {gas: 'C', power: 'electrical'};
    var HAZARD_ACTION = {gas: 'Gaszufuhr absperren', power: 'Strom abschalten'};
    var HAZARD_BUTTON = {gas: '🔧 Gas absperren', power: '⚡ Strom abschalten'};
    var HAZARD_WARN = {gas: 'Bei Gasbränden zuerst die Gaszufuhr absperren!',
                       power: 'Bei Elektrobränden zuerst den Strom abschalten!'};
    function gatedHazardFor(cls){
      if (!level || !level.supplies) return null;
      for (var i=0;i<level.supplies.length;i++){ if (HAZARD_CLASS[level.supplies[i]]===cls) return level.supplies[i]; }
      return null;
    }
    // Which hazard (if any) feeds this class, among a running game's supplies.
    function HAZARD_CLASS_OF_IN(g, cls){
      for (var h in g.supplies){ if (Object.prototype.hasOwnProperty.call(g.supplies,h) && HAZARD_CLASS[h]===cls) return h; }
      return null;
    }
    function rightActionFor(cid){
      var h=gatedHazardFor(cid);
      if (h) return HAZARD_ACTION[h];
      var c=classMap[cid]||{}; return c.right_tool_de||'';
    }

    var canvas = document.getElementById('board');
    var ctx = canvas.getContext('2d');
    var level = null;       // the loaded level's map + waves + schedule
    var classMap = {};      // class id -> {icon, colour, letter, name_de}
    var toolMap = {};       // tool id -> {name_de, cost, short, hex}
    var toolsList = [];
    var matrixMap = {};     // "class|tool" -> outcome (good/weak/useless/danger)
    var reasonMap = {};     // "class|tool" -> Anton's feedback line (ITEM-012)
    var seen = {};          // fire classes already introduced this session (ITEM-011)
    var cardsEnabled = true;
    var paused = false;     // true while an explanation card is up
    var feedbackUntil = 0;
    var selectedTool = null;
    var sprays = [];        // brief tower->fire lines to draw: {x1,y1,x2,y2,until}
    var game = null;        // running game state, or null before start
    var last = 0;

    function pathLength(wp) {
      var t = 0;
      for (var i = 1; i < wp.length; i++) t += Math.hypot(wp[i][0]-wp[i-1][0], wp[i][1]-wp[i-1][1]);
      return t;
    }
    // Same maths as the server's path_point_at: a point a fraction t along the path.
    function pathPointAt(wp, t) {
      if (!wp.length) return [0,0];
      if (t <= 0) return wp[0];
      if (t >= 1) return wp[wp.length-1];
      var total = pathLength(wp); if (!total) return wp[0];
      var target = t*total, walked = 0;
      for (var i = 1; i < wp.length; i++) {
        var seg = Math.hypot(wp[i][0]-wp[i-1][0], wp[i][1]-wp[i-1][1]);
        if (seg && walked + seg >= target) {
          var f = (target-walked)/seg;
          return [wp[i-1][0]+(wp[i][0]-wp[i-1][0])*f, wp[i-1][1]+(wp[i][1]-wp[i-1][1])*f];
        }
        walked += seg;
      }
      return wp[wp.length-1];
    }

    // --- drawing ---
    function trace(wp) { ctx.beginPath(); ctx.moveTo(wp[0][0], wp[0][1]); for (var i=1;i<wp.length;i++) ctx.lineTo(wp[i][0],wp[i][1]); }
    function drawPath(wp) {
      ctx.lineCap='round'; ctx.lineJoin='round';
      ctx.strokeStyle='#cbb79f'; ctx.lineWidth=40; trace(wp); ctx.stroke();
      ctx.strokeStyle='#a8a29e'; ctx.lineWidth=30; trace(wp); ctx.stroke();
    }
    function drawBuildSpot(x,y){ ctx.setLineDash([6,6]); ctx.strokeStyle='#0369a1'; ctx.lineWidth=3; ctx.beginPath(); ctx.arc(x,y,22,0,Math.PI*2); ctx.stroke(); ctx.setLineDash([]); }
    function drawStart(wp){ ctx.fillStyle='#c2410c'; ctx.beginPath(); ctx.arc(wp[0][0],wp[0][1],9,0,Math.PI*2); ctx.fill(); ctx.font='12px system-ui'; ctx.textAlign='center'; ctx.fillText('Start', wp[0][0], wp[0][1]-15); }
    function drawBuilding(b){
      var flashing = game && performance.now() < game.flashUntil;
      var w=74,h=60;
      ctx.fillStyle = flashing ? '#dc2626' : '#15803d'; ctx.fillRect(b.x-w/2,b.y-h/2,w,h);
      ctx.beginPath(); ctx.moveTo(b.x-w/2-8,b.y-h/2); ctx.lineTo(b.x,b.y-h/2-32); ctx.lineTo(b.x+w/2+8,b.y-h/2); ctx.closePath();
      ctx.fillStyle = flashing ? '#991b1b' : '#166534'; ctx.fill();
      ctx.fillStyle='#fde68a'; ctx.fillRect(b.x-10,b.y-2,20,h/2+2);
      ctx.fillStyle='#14532d'; ctx.font='13px system-ui'; ctx.textAlign='center';
      ctx.fillText(b.name_de||'Gebäude', b.x, b.y+h/2+18);
    }
    function drawFire(f){
      var p = pathPointAt(game.level.path, f.progress);
      var cls = classMap[f.cls] || {icon:'🔥', colour:'#dc2626', letter:'?'};
      var reacting = f.reaction && performance.now() < (f.reactionUntil||0);
      // soft animated glow behind the fire (cartoon flame feel), colour = its class
      var pulse = 24 + Math.sin(performance.now()/180 + p[0]) * 3;
      var grad = ctx.createRadialGradient(p[0],p[1],3, p[0],p[1],pulse);
      grad.addColorStop(0, cls.colour); grad.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.save(); ctx.globalAlpha=0.35; ctx.fillStyle=grad;
      ctx.beginPath(); ctx.arc(p[0],p[1],pulse,0,Math.PI*2); ctx.fill(); ctx.restore();
      if (reacting && f.reaction==='danger'){
        ctx.beginPath(); ctx.arc(p[0],p[1],25,0,Math.PI*2); ctx.strokeStyle='#b91c1c'; ctx.lineWidth=4; ctx.stroke();
      } else if (reacting && f.reaction==='useless'){
        ctx.setLineDash([4,4]); ctx.beginPath(); ctx.arc(p[0],p[1],24,0,Math.PI*2); ctx.strokeStyle='#9ca3af'; ctx.lineWidth=3; ctx.stroke(); ctx.setLineDash([]);
      }
      ctx.beginPath(); ctx.arc(p[0],p[1],17,0,Math.PI*2); ctx.fillStyle=cls.colour; ctx.fill();
      ctx.lineWidth=2; ctx.strokeStyle='#fff'; ctx.stroke();
      ctx.font='18px system-ui'; ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillText(cls.icon, p[0], p[1]+1);
      ctx.beginPath(); ctx.arc(p[0]+15,p[1]-15,8,0,Math.PI*2); ctx.fillStyle='#111827'; ctx.fill();
      ctx.fillStyle='#fff'; ctx.font='bold 10px system-ui'; ctx.fillText(cls.letter, p[0]+15, p[1]-14);
      if (reacting && f.reaction==='danger'){ ctx.font='15px system-ui'; ctx.fillText('⚠️', p[0], p[1]-26); }
      ctx.textBaseline='alphabetic';
    }
    function drawOverlay(){
      // Just a soft dim when the level is over; the detailed recap is an HTML modal.
      if (!game || game.status==='playing' || game.status==='idle') return;
      ctx.fillStyle='rgba(255,247,237,.55)'; ctx.fillRect(0,0,canvas.width,canvas.height);
    }

    function showRecap(){
      if (!game) return;
      var total=game.schedule.length, handled=game.ext;
      var knowledge = total ? Math.round(100*handled/total) : 0;
      document.getElementById('recapTitle').textContent =
        game.status==='won' ? 'Einsatz geschafft! 🎉' : 'Einsatz gescheitert';
      document.getElementById('recapTitle').style.color = game.status==='won' ? '#15803d' : '#b91c1c';
      document.getElementById('recapScore').textContent = 'Wissenswertung: ' + knowledge + '%';
      document.getElementById('recapLine').textContent =
        handled + ' von ' + total + ' Feuern richtig gelöscht · ' + game.leaked +
        ' durchgekommen · ' + (game.danger+game.useless) + ' Fehlversuche';
      var rows='';
      var seen={};
      game.schedule.forEach(function(ev){
        if (seen[ev['class']]) return; seen[ev['class']]=true;
        var c=classMap[ev['class']]||{};
        rows += '<div style="display:flex; align-items:center; gap:.5rem; padding:.25rem 0; border-top:1px solid #f0e6da;">' +
                '<span style="font-size:1.3rem;">'+(c.icon||'🔥')+'</span>' +
                '<span style="flex:1;">'+(c.name_de||ev['class'])+'</span>' +
                '<span style="color:#15803d;">Richtig: '+(rightActionFor(ev['class'])||'')+'</span></div>';
      });
      document.getElementById('recapClasses').innerHTML =
        '<div style="color:#9a6a4f; margin-bottom:.2rem;">Diese Feuer kamen vor:</div>' + rows;
      document.getElementById('recap').style.display='flex';
    }

    function buildLib(){
      var body=document.getElementById('libBody'); if (!body) return;
      var rows='';
      (window._classOrder||[]).forEach(function(cid){
        var c=classMap[cid]||{};
        var goods=[], dangers=[];
        (toolsList||[]).forEach(function(t){
          var o=matrixMap[cid+'|'+t.id];
          if (o==='good') goods.push(t.short);
          else if (o==='danger') dangers.push(t.short);
        });
        rows += '<div style="padding:.5rem 0; border-top:1px solid #f0e6da;">' +
          '<div style="font-weight:600;">'+(c.icon||'🔥')+' '+(c.name_de||cid)+'</div>' +
          '<div style="color:#7c2d12;">'+(c.card_de||'')+'</div>' +
          '<div style="color:#15803d;">✓ Richtig: '+(goods.join(', ')||'—')+'</div>' +
          (dangers.length ? '<div style="color:#b91c1c;">⚠️ Gefährlich: '+dangers.join(', ')+'</div>' : '') +
          '</div>';
      });
      body.innerHTML = rows || '<p>Wird geladen …</p>';
    }
    function openLib(){ buildLib(); if (game && game.status==='playing') paused=true; document.getElementById('lib').style.display='flex'; }
    function closeLib(){ document.getElementById('lib').style.display='none'; paused=false; last=performance.now(); }

    // --- game logic (mirrors the server's GameState) ---
    function firePos(f){ return pathPointAt(game.level.path, f.progress); }
    function nearestFireInRange(tw){
      var bx=tw.spot[0], by=tw.spot[1], best=null, bestD=null;
      for (var i=0;i<game.fires.length;i++){
        var p=firePos(game.fires[i]); var d=Math.hypot(p[0]-bx, p[1]-by);
        if (d<=TOWER_RANGE && (bestD===null || d<bestD)){ best=game.fires[i]; bestD=d; }
      }
      return best;
    }
    function advance(dt){
      var g = game; if (!g || g.status!=='playing') return;
      g.elapsed += dt;
      // spawn (schedule comes from the server; key is "class")
      while (g.spawned < g.schedule.length && g.schedule[g.spawned].t <= g.elapsed){
        var scls = g.schedule[g.spawned]["class"];
        var shaz = HAZARD_CLASS_OF_IN(g, scls);
        if (shaz && g.supplies[shaz]==='off'){
          // its supply is already cut — this fire never really starts (counted handled)
          g.ext++; g.spawned++; continue;
        }
        g.fires.push({id:g.nextId++, cls:scls, progress:0}); g.spawned++;
      }
      // towers fire at the nearest fire in range; the outcome depends on the matrix
      for (var ti=0; ti<g.towers.length; ti++){
        var tw=g.towers[ti]; tw.cooldown-=dt;
        if (tw.cooldown>0) continue;
        var target=nearestFireInRange(tw);
        if (!target) continue;
        tw.cooldown = TOWER_COOLDOWN;
        var tp=firePos(target);
        sprays.push({x1:tw.spot[0], y1:tw.spot[1], x2:tp[0], y2:tp[1], until:performance.now()+120});
        var thaz = HAZARD_CLASS_OF_IN(g, target.cls);
        if (thaz && g.supplies[thaz]==='on'){
          // supply still on: spraying does nothing — cut the supply first
          target.reaction='useless'; target.reactionUntil=performance.now()+500;
          showFeedback(HAZARD_WARN[thaz], 'danger');
          g.useless++;
          continue;
        }
        var outcome = matrixMap[target.cls + '|' + tw.tool];
        if (outcome==='good' || outcome==='weak'){
          g.fires = g.fires.filter(function(f){ return f.id!==target.id; });
          g.budget += EXTINGUISH_REWARD + (outcome==='good' ? SMART_BONUS : 0); updateBudget();
          g.ext++;
        } else if (outcome==='danger'){
          target.progress = Math.min(0.999, target.progress + DANGER_SPEEDUP);
          target.reaction='danger'; target.reactionUntil=performance.now()+500;
          showFeedback(reasonMap[target.cls + '|' + tw.tool], 'danger');
          g.danger++;
        } else {
          target.reaction='useless'; target.reactionUntil=performance.now()+500;
          showFeedback(reasonMap[target.cls + '|' + tw.tool], 'useless');
          g.useless++;
        }
      }
      // move fires; arrivals cost a life
      var still=[];
      for (var i=0;i<g.fires.length;i++){
        var f=g.fires[i]; f.progress += g.speed*dt;
        if (f.progress>=1){ g.lives--; g.leaked++; g.flashUntil=performance.now()+350; } else still.push(f);
      }
      g.fires=still;
      if (g.lives<=0){ g.lives=0; g.status='lost'; return; }
      if (g.spawned>=g.schedule.length && g.fires.length===0){ g.status='won'; }
    }

    // A fresh game for a level: 'idle' until "Einsatz starten". Towers can be
    // placed while idle (build first) and while playing.
    function newGame(lv){
      var sup={}; (lv.supplies||[]).forEach(function(h){ sup[h]='on'; });
      return { level:lv, schedule:(lv.schedule||[]),
               speed: FIRE_PX_PER_SEC / pathLength(lv.path),
               lives: lv.building.lives, budget: lv.budget||0,
               elapsed:0, spawned:0, fires:[], nextId:0,
               towers:[], nextTowerId:0, status:'idle', flashUntil:0,
               ext:0, danger:0, useless:0, leaked:0, supplies:sup };
    }
    function onStartButton(){
      if (!game) return;
      if (game.status==='idle'){ game.status='playing'; last=performance.now(); }
      else if (game.status==='won' || game.status==='lost'){ game=newGame(level); sprays=[]; }
      updateControls(); updateBudget();
    }

    function towerAt(idx){
      if (!game) return null;
      for (var i=0;i<game.towers.length;i++) if (game.towers[i].spot_index===idx) return game.towers[i];
      return null;
    }
    function placeTower(spotIndex, toolId){
      if (!game || !level) return false;
      var spots=level.build_spots;
      if (spotIndex<0 || spotIndex>=spots.length) return false;
      if (towerAt(spotIndex)) return false;                 // spot taken
      var cost=(toolMap[toolId]||{}).cost||0;
      if (cost<=0 || game.budget<cost) return false;        // can't afford
      game.budget-=cost;
      game.towers.push({id:game.nextTowerId++, spot_index:spotIndex, spot:spots[spotIndex], tool:toolId, cooldown:0});
      updateBudget();
      return true;
    }

    // Cut a supply (ITEM-016): puts out the fires it fed and stops them being a threat.
    function shutOff(hazard){
      var g=game; if (!g || !g.supplies || g.supplies[hazard]!=='on') return;
      if (g.status==='won' || g.status==='lost') return;
      g.supplies[hazard]='off';
      var cls=HAZARD_CLASS[hazard];
      var out=g.fires.filter(function(f){ return f.cls===cls; });
      if (out.length){
        g.fires=g.fires.filter(function(f){ return f.cls!==cls; });
        for (var i=0;i<out.length;i++){ g.ext++; g.budget+=EXTINGUISH_REWARD; }
        updateBudget();
      }
      if (g.status==='playing' && g.spawned>=g.schedule.length && g.fires.length===0){ g.status='won'; }
      showFeedback(hazard==='gas' ? 'Gaszufuhr abgesperrt — gut!' : 'Strom abgeschaltet — gut!', 'ok');
      renderHazardControls();
    }

    // The "cut the supply" buttons a level offers (only the hazards it declares).
    function renderHazardControls(){
      var bar=document.getElementById('hazardControls'); if (!bar) return;
      bar.innerHTML='';
      var sup=(level && level.supplies) || [];
      sup.forEach(function(h){
        var btn=document.createElement('button');
        var off = game && game.supplies && game.supplies[h]==='off';
        var over = game && (game.status==='won' || game.status==='lost');
        btn.textContent = HAZARD_BUTTON[h] + (off ? ' ✓' : '');
        btn.disabled = off || over;
        btn.onclick = function(){ shutOff(h); };
        bar.appendChild(btn);
      });
    }

    function updateBudget(){
      var b = game ? game.budget : (level ? (level.budget||0) : 0);
      document.getElementById('budget').textContent = '💰 ' + b;
      Array.prototype.forEach.call(document.querySelectorAll('#toolPalette button'), function(btn){
        var cost=parseInt(btn.getAttribute('data-cost'),10);
        btn.disabled = (b < cost);
        btn.classList.toggle('active', btn.getAttribute('data-tool')===selectedTool);
      });
    }

    function drawTower(tw){
      var t=toolMap[tw.tool]||{hex:'#334155', short:'?'};
      var x=tw.spot[0], y=tw.spot[1];
      ctx.beginPath(); ctx.arc(x,y,TOWER_RANGE,0,Math.PI*2); ctx.fillStyle='rgba(2,132,199,.05)'; ctx.fill();
      ctx.beginPath(); ctx.arc(x,y,20,0,Math.PI*2); ctx.fillStyle=t.hex; ctx.fill();
      ctx.lineWidth=3; ctx.strokeStyle='#fff'; ctx.stroke();
      ctx.fillStyle='#fff'; ctx.font='bold 9px system-ui'; ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillText((t.short||'').slice(0,6), x, y);
      ctx.textBaseline='alphabetic';
    }
    function drawSprays(){
      var now=performance.now(), keep=[];
      for (var i=0;i<sprays.length;i++){ var s=sprays[i]; if (s.until<now) continue; keep.push(s);
        ctx.strokeStyle='rgba(255,255,255,.85)'; ctx.lineWidth=3;
        ctx.beginPath(); ctx.moveTo(s.x1,s.y1); ctx.lineTo(s.x2,s.y2); ctx.stroke();
      }
      sprays=keep;
    }

    function setLives(n){ var s=''; for (var i=0;i<n;i++) s+='❤️'; document.getElementById('lives').textContent = s + '  (' + n + ')'; }
    function currentWave(){ if (!game || !game.spawned) return 0; return game.schedule[game.spawned-1].wave + 1; }
    function totalWaves(){ return level && level.waves ? level.waves.length : 0; }
    function infoText(){
      if (!game || game.status==='idle') return totalWaves() + ' Wellen — Löscher bauen, dann starten.';
      if (game.status==='won') return 'Gewonnen!';
      if (game.status==='lost') return 'Verloren.';
      return 'Welle ' + currentWave() + ' / ' + totalWaves() + ' · ' + game.fires.length + ' Feuer';
    }
    function updateControls(){
      var btn=document.getElementById('startBtn');
      if (!game || game.status==='idle'){ btn.textContent='Einsatz starten'; btn.disabled=false; }
      else if (game.status==='playing'){ btn.textContent='Läuft …'; btn.disabled=true; }
      else { btn.textContent='Neu starten'; btn.disabled=false; }
      renderHazardControls();
    }

    function drawTree(x,y){ ctx.fillStyle='#6aa84f'; ctx.beginPath(); ctx.arc(x,y,24,0,Math.PI*2); ctx.fill(); ctx.fillStyle='#7a5230'; ctx.fillRect(x-4,y+16,8,16); }
    function drawBackground(){
      var w=canvas.width, h=canvas.height;
      var park = level && level.index===1;
      ctx.fillStyle = park ? '#eef6e7' : '#f6ecdd';
      ctx.fillRect(0,0,w,h);
      // a couple of low-key corner decorations, kept away from the play area
      ctx.save(); ctx.globalAlpha=0.5;
      if (park){ drawTree(40,h-40); drawTree(w-40,40); }
      else {
        ctx.strokeStyle='#e4d3ba'; ctx.lineWidth=5;
        ctx.strokeRect(20,h-70,90,55); ctx.beginPath(); ctx.moveTo(20,h-70); ctx.lineTo(110,h-15); ctx.moveTo(110,h-70); ctx.lineTo(20,h-15); ctx.stroke();
      }
      ctx.restore();
    }
    function drawAnton(){
      var now=performance.now();
      var x=canvas.width-44, y=42 + Math.sin(now/500)*6;
      ctx.save();
      ctx.fillStyle='rgba(226,232,240,.92)';
      ctx.beginPath(); ctx.arc(x,y,18,Math.PI,0);
      ctx.lineTo(x+18,y+16);
      ctx.quadraticCurveTo(x+9,y+24, x, y+16);
      ctx.quadraticCurveTo(x-9,y+24, x-18, y+16);
      ctx.closePath(); ctx.fill();
      ctx.fillStyle='#334155';
      ctx.beginPath(); ctx.arc(x-6,y-2,3,0,Math.PI*2); ctx.arc(x+6,y-2,3,0,Math.PI*2); ctx.fill();
      // little crooked fire helmet
      ctx.save(); ctx.translate(x,y-15); ctx.rotate(-0.2); ctx.fillStyle='#dc2626';
      ctx.fillRect(-13,-2,26,5); ctx.beginPath(); ctx.arc(0,0,8,Math.PI,0); ctx.fill(); ctx.restore();
      ctx.restore();
    }

    function render(){
      if (!level) return;
      ctx.clearRect(0,0,canvas.width,canvas.height);
      drawBackground();
      drawPath(level.path);
      level.build_spots.forEach(function(s, idx){ var tw=towerAt(idx); if (tw) drawTower(tw); else drawBuildSpot(s[0],s[1]); });
      drawStart(level.path);
      drawBuilding(level.building);
      drawAnton();
      if (game){
        game.fires.forEach(drawFire);
        drawSprays();
        setLives(game.lives);
        drawOverlay();
      } else {
        setLives(level.building.lives);
      }
      document.getElementById('info').textContent = infoText();
    }

    function showFeedback(msg, kind){
      if (!msg) return;
      var el=document.getElementById('feedback');
      el.textContent = (kind==='danger' ? '⚠️ ' : '') + 'Anton: ' + msg;
      el.style.color = (kind==='danger') ? '#b91c1c' : '#9a6a4f';
      feedbackUntil = performance.now() + 2600;
    }
    function showCard(cls){
      var c=classMap[cls]||{}; paused=true;
      document.getElementById('cardIcon').textContent = c.icon || '🔥';
      document.getElementById('cardTitle').textContent = (c.name_de||'') + (c.letter ? (' ('+c.letter+')') : '');
      document.getElementById('cardText').textContent = c.card_de || '';
      document.getElementById('card').style.display = 'flex';
    }
    function maybeShowCard(){
      if (!cardsEnabled || !game) return;
      for (var i=0;i<game.fires.length;i++){
        var cls=game.fires[i].cls;
        if (!seen[cls]){ seen[cls]=true; showCard(cls); return; }
      }
    }

    var prevStatus='idle';
    function frame(now){
      var dt = Math.min((now - last)/1000, 0.05); last = now;
      if (game && game.status==='playing' && !paused){ advance(dt); maybeShowCard(); }
      if (performance.now() > feedbackUntil) document.getElementById('feedback').textContent='';
      render();
      if (game && game.status!==prevStatus){
        if (game.status==='won' || game.status==='lost') showRecap();
        updateControls();
        prevStatus = game.status;
      }
      requestAnimationFrame(frame);
    }

    function loadLevel(i){
      fetch('/api/level/'+i).then(function(r){return r.json();}).then(function(data){
        if (data.error) return;
        level = data; game = newGame(level); sprays = []; prevStatus='idle';
        seen = {}; paused = false;
        document.getElementById('card').style.display = 'none';
        document.getElementById('recap').style.display = 'none';
        document.getElementById('feedback').textContent = '';
        canvas.width = data.size.w; canvas.height = data.size.h;
        document.getElementById('place').textContent = data.name + ' · ' + data.place_de;
        setLives(data.building.lives);
        updateControls(); updateBudget();
        Array.prototype.forEach.call(document.querySelectorAll('#levelBar button'), function(btn, idx){
          btn.className = (idx===i) ? 'active' : '';
        });
      }).catch(function(){ document.getElementById('place').textContent='Einsatz konnte nicht geladen werden.'; });
    }

    function loadTools(){
      return fetch('/api/tools').then(function(r){return r.json();}).then(function(list){
        toolsList=list; var bar=document.getElementById('toolPalette'); bar.innerHTML='';
        list.forEach(function(t){
          toolMap[t.id]=t;
          var btn=document.createElement('button');
          btn.textContent=t.short+' ('+t.cost+')';
          btn.setAttribute('data-tool', t.id); btn.setAttribute('data-cost', t.cost);
          btn.onclick=function(){ selectedTool=t.id; updateBudget(); };
          bar.appendChild(btn);
        });
      }).catch(function(){});
    }

    // Tap/click a build spot to place the selected tool there.
    canvas.addEventListener('click', function(e){
      if (!game || !selectedTool || !level) return;
      var rect=canvas.getBoundingClientRect();
      var x=(e.clientX-rect.left)*(canvas.width/rect.width);
      var y=(e.clientY-rect.top)*(canvas.height/rect.height);
      var spots=level.build_spots, bestI=-1, bestD=null;
      for (var i=0;i<spots.length;i++){
        var d=Math.hypot(spots[i][0]-x, spots[i][1]-y);
        if (d<=32 && (bestD===null || d<bestD)){ bestD=d; bestI=i; }
      }
      if (bestI>=0) placeTower(bestI, selectedTool);
    });

    function buildLevelBar(){
      fetch('/api/levels').then(function(r){return r.json();}).then(function(list){
        var bar=document.getElementById('levelBar');
        list.forEach(function(lv){
          var btn=document.createElement('button');
          btn.textContent=(lv.index+1)+'. '+lv.name;
          btn.onclick=function(){ loadLevel(lv.index); };
          bar.appendChild(btn);
        });
        loadLevel(0);
      });
    }

    function loadClasses(){
      return fetch('/api/classes').then(function(r){return r.json();}).then(function(list){
        var leg=document.getElementById('classLegend'); leg.innerHTML='';
        window._classOrder = list.map(function(c){ return c.id; });
        list.forEach(function(c){
          classMap[c.id]=c;
          var el=document.createElement('span'); el.style.color=c.colour;
          el.textContent=c.icon+' '+c.name_de+' ('+c.letter+')'; leg.appendChild(el);
        });
      }).catch(function(){});
    }

    function loadMatrix(){
      return fetch('/api/matrix').then(function(r){return r.json();}).then(function(list){
        matrixMap={}; reasonMap={};
        list.forEach(function(x){
          matrixMap[x['class'] + '|' + x.tool] = x.outcome;
          if (x.reason) reasonMap[x['class'] + '|' + x.tool] = x.reason;
        });
      }).catch(function(){});
    }

    function loadStatus(){
      fetch('/health').then(function(r){return r.json();}).then(function(h){
        document.getElementById('foot').textContent =
          'Datenbank ' + (h.status==='ok'?'bereit':'fehlt') + ' · ' + h.fire_classes + ' Brandklassen · ' + h.tools + ' Löschmittel';
      }).catch(function(){});
    }

    document.getElementById('startBtn').onclick = onStartButton;
    document.getElementById('cardOk').onclick = function(){
      document.getElementById('card').style.display='none'; paused=false; last=performance.now();
    };
    document.getElementById('cardsToggle').onchange = function(e){ cardsEnabled = e.target.checked; };
    document.getElementById('libBtn').onclick = openLib;
    document.getElementById('libClose').onclick = closeLib;
    document.getElementById('recapLib').onclick = openLib;
    document.getElementById('recapAgain').onclick = function(){
      document.getElementById('recap').style.display='none'; onStartButton();
    };
    // Load classes, tools, and the fire-safety matrix first (the view, palette, and
    // shot resolution need them), then the levels.
    Promise.all([loadClasses(), loadTools(), loadMatrix()]).then(function(){ buildLevelBar(); });
    loadStatus();
    last = performance.now();
    requestAnimationFrame(frame);
  </script>
</body>
</html>"""


# --- Web app -----------------------------------------------------------------

@asynccontextmanager
async def _lifespan(_app):
    # The database builds itself on every start. On free hosting whose disk is
    # wiped between restarts (decided in ITEM-002), this is exactly what keeps the
    # app self-contained: nothing needs to be uploaded separately. (Uses the modern
    # "lifespan" startup hook rather than the deprecated on_event style.)
    init_db()
    yield


app = FastAPI(title=APP_TITLE, lifespan=_lifespan)


@app.get("/health")
def health() -> JSONResponse:
    """A tiny check a person or a hosting provider can hit to confirm it's alive."""
    return JSONResponse(health_payload())


@app.get("/api/levels")
def api_levels() -> JSONResponse:
    """The list of levels, for the level switcher."""
    return JSONResponse(levels_index())


@app.get("/api/level/{index}")
def api_level(index: int) -> JSONResponse:
    """One level's map data (path, build spots, building, waves) for the browser."""
    data = level_json(index)
    if data is None:
        return JSONResponse({"error": "no such level"}, status_code=404)
    return JSONResponse(data)


@app.get("/api/classes")
def api_classes() -> JSONResponse:
    """Display info per fire class (icon, colour, letter) for drawing + the legend."""
    return JSONResponse(classes_display())


@app.get("/api/tools")
def api_tools() -> JSONResponse:
    """Tool palette info (name, cost, short label, colour) for placing towers."""
    return JSONResponse(tools_display())


@app.get("/api/matrix")
def api_matrix() -> JSONResponse:
    """The fire-safety matrix from the database (class × tool → outcome). The browser
    resolves each shot against this — the facts are never hard-coded in the browser."""
    m = load_matrix()
    return JSONResponse([
        {"class": c, "tool": t, "outcome": o, "reason": feedback_reason(c, t)}
        for (c, t), o in m.items()
    ])


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    """The game view — draws the level map with a marker travelling the path."""
    return render_game_html()


# --- Run ---------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # `--check-content` runs the fire-facts check and exits — no server, no web
    # framework needed. This is what the automatic checks (CI) and the pre-save
    # hook call.
    if "--check-content" in sys.argv:
        init_db()
        ok1, p1 = check_content()
        ok2, p2 = check_levels()
        if ok1 and ok2:
            nc, nt = content_counts()
            print(f"Checks PASSED — {nc} Brandklassen, {nt} Löschmittel, "
                  f"{level_count()} Level, alle Prüfungen bestanden.")
            sys.exit(0)
        print("Checks FAILED:")
        for p in p1 + p2:
            print("  -", p)
        sys.exit(1)

    # `--simulate` plays the first level to the end with several strategies and
    # confirms only safe, correct play wins. Exits 0 if the game still teaches, 1 if
    # a change has made it winnable the wrong way. No server, no web request needed.
    if "--simulate" in sys.argv:
        ok, problems = behaviour_check()
        if ok:
            print("Behaviour check PASSED — the first level is only won by safe, correct play.")
            sys.exit(0)
        print("Behaviour check FAILED:")
        for p in problems:
            print("  -", p)
        sys.exit(1)

    import uvicorn

    # Build the database before we start serving, so the very first request works
    # even if the startup event hasn't run yet in some setups.
    init_db()
    print(f"Firefighter Defense läuft auf  http://{HOST}:{PORT}")
    print(f"Datenbank: {DATABASE_PATH}")
    uvicorn.run(app, host=HOST, port=PORT)
