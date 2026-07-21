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
from functools import lru_cache
from contextlib import asynccontextmanager, closing

# NOTE (ITEM-026/027 headless-testing unlock): FastAPI is imported lazily inside
# build_app() below, NOT at module import time. That lets the command-line logic
# (--check-content, --simulate) and the test suite import this module and run the
# real game logic on machines where the web framework isn't installed (e.g. an
# offline sandbox). The web routes and their behaviour are unchanged — only *where*
# they're defined moved.

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

# =============================================================================
# ANTON — every line the castle ghost speaks, gathered in ONE labelled place
# =============================================================================
# DECISION (Adam, ITEM-026): keep ALL of Anton's text together, in this single
# file, edited in this one spot — his "meet-the-fire" cards, his wrong-tool
# feedback, the per-mission openings/anecdotes/hints/closings (ITEM-027), and the
# supply-hazard warnings. Nothing about Anton is written anywhere else in the code;
# everything below is data the rest of the program reads.
#
# Translation-ready (ITEM-001, German-first, English possible later): every line is
# an L(...) node with a German string now and room for an English string beside it.
# Only German is filled in today. To add English later, fill each node's "en".
#
# Anton's voice, kept consistent everywhere below: warm and encouraging, never
# scolding; proud of the Freiwillige Feuerwehr Königstein; and endearingly
# water-shy — but the joke is always that ANTON personally fears water, never that
# water is a bad tool. On an ordinary wood/paper fire (Class A) water is correct,
# and his lines never suggest otherwise. Any fire advice in his prose points to the
# fire-safety reference's correct action for that fire (guarded by check_narration).

def L(de: str, en: str | None = None) -> dict:
    """One of Anton's lines, ready for translation: German now, English later."""
    return {"de": de, "en": en}


ANTON = {
    # --- "Meet the fire" cards (ITEM-011): shown once per class, in Anton's voice.
    #     Facts stay true to FIRE_SAFETY_REFERENCE.md.
    "class_cards": {
        "A": L("Holz, Papier, Stoff — ein ganz gewöhnliches Feuer. Keine Sorge: Wasser, Schaum oder Pulver löschen es sicher. (Ich halte beim Wasser nur lieber etwas Abstand …)"),
        "B": L("Brennende Flüssigkeit! Kein Wasser, das spritzt nur. Schaum, Pulver oder CO₂ ersticken die Flammen."),
        "C": L("Brennendes Gas. Wenn möglich zuerst die Gaszufuhr absperren! Pulver hält die Flamme in Schach."),
        "electrical": L("Da steht etwas unter Strom. Bloß kein Wasser — Stromschlag! Am besten CO₂ (und den Strom abschalten)."),
        "D": L("Brennendes Metall — heikel. Nur das Spezial-Metallbrandpulver hilft. Wasser wäre gefährlich."),
        "F": L("Fett in der Fritteuse brennt. NIE Wasser — das gibt eine Stichflamme! Der Fettbrandlöscher hilft."),
    },
    # --- Wrong-tool feedback (ITEM-012). Danger reasons keyed "class|tool"; the
    #     glue templates build the kind, never-scolding one-liner around them.
    "danger_reasons": {
        "F|water": L("Wasser im Fettbrand führt zur Fettexplosion (Stichflamme)."),
        "electrical|water": L("Wasser leitet Strom – Stromschlaggefahr."),
        "electrical|foam": L("Schaum leitet Strom – nicht auf Spannung."),
        "electrical|wetchem": L("Fettbrandlöscher leitet Strom – nicht auf Elektrobrand."),
        "D|water": L("Wasser auf brennendem Metall reagiert heftig."),
        "D|foam": L("Wasserbasiertes Mittel auf Metall reagiert heftig."),
        "D|wetchem": L("Wasserbasiertes Mittel auf Metall reagiert heftig."),
        "B|water": L("Wasser verteilt die brennende Flüssigkeit."),
        "F|foam": L("Wasserbasiertes Mittel im Fettbrand – Stichflammengefahr."),
        "F|co2": L("CO₂ kann brennendes Fett wegschleudern."),
    },
    "feedback": {
        "danger_fallback": L("Das macht es nur schlimmer!"),
        "danger_suffix": L(" Nimm lieber {tool}."),
        "useless": L("Das wirkt hier leider nicht."),
        "useless_suffix": L(" Nimm {tool}."),
    },
    # --- Supply-hazard warnings (ITEM-016): shown when a fire is sprayed before its
    #     gas/power supply is cut.
    "hazard_warn": {
        "gas": L("Bei Gasbränden zuerst die Gaszufuhr absperren!"),
        "power": L("Bei Elektrobränden zuerst den Strom abschalten!"),
    },
    # --- Per-mission framing (ITEM-027): Anton opens each story mission by SENSING
    #     the trouble (marked on the map) and telling a local Königstein ANECDOTE,
    #     whispers ONE light, safe tactical HINT during play, and CLOSES with a short
    #     reflection. Optional "bonus" line is Anton's narration when a mission is won
    #     with nothing leaking (the people/records/stage kept safe) — pure story on
    #     top of the unchanged tower-defense core (ITEM-030), never a second win path.
    #
    #     Guard (check_narration): a hint must never name a tool that is DANGEROUS on
    #     one of that mission's fires as the thing to USE. Positive tool mentions in a
    #     hint therefore stick to tools that are correct-and-never-dangerous across the
    #     whole mission; dangerous tools appear only under a warning ("nie/kein …").
    "missions": {
        "fachwerk": {
            "open": L("Riechst du das? Rauch zieht durch die Fachwerkgasse. Ich, Anton, spüre so etwas immer zuerst — hier bricht gleich Feuer aus. Schnell, die Wehr braucht dich!"),
            "anecdote": L("Diese Gasse kenne ich seit 150 Jahren. Vor achtzig Jahren sprang hier schon einmal ein Funke von Balken zu Balken — die halbe Nachbarschaft stand mit Eimern bereit. In dem Haus dort wohnt ein altes Ehepaar, das Andenken an unsere Feuerwehr hütet. Die beschützen wir heute."),
            "hint": L("Aus der Backstube kriechen Fettbrände — die brauchen ihren eigenen Löscher, niemals Wasser. Auf Holz und Strom ist das ABC-Pulver ein guter Freund, aber bloß kein Wasser auf die Leitung!"),
            "close": L("Geschafft! Die Balken halten, das Ehepaar ist sicher. Weißt du, jedes Mal, wenn ich unsere Wehr so arbeiten sehe, wird mir ganz warm ums Geisterherz. Auf zum nächsten Einsatz!"),
            "bonus": L("Rettungsbonus: Das alte Ehepaar und seine Andenken sind unversehrt."),
        },
        "bibliothek": {
            "open": L("In meiner Burg — der Burgbibliothek! Ich spüre heiße Luft zwischen den Regalen. Eine alte Leitung glimmt und hat schon ein paar Bücher entzündet. Bitte, sei behutsam mit meinen Protokollen!"),
            "anecdote": L("Hier lagern Einsatzprotokolle aus 150 Jahren. Vielleicht steht in einer dieser Kisten sogar mein eigener Name — der junge Burgwächter, der blieb. Nur: Wasser würde die alten Seiten für immer ruinieren. Am liebsten ist mir, wenn gar nichts auf die Papiere spritzt."),
            "hint": L("Zuerst den Strom abschalten — das ist der sauberste Weg, ganz ohne Wasser auf den kostbaren Protokollen. Die brennenden Bücher sind ein gewöhnliches Feuer; nur die Leitung verträgt niemals Wasser."),
            "close": L("Der Strom ist aus, die Bücher gerettet — und kein Blatt ist nass geworden! Schau, hier … „Anton, treuer Wächter der Burg“. Zum ersten Mal seit 150 Jahren fühle ich mich wirklich gesehen. Danke, dass du meine Geschichte gerettet hast."),
            "bonus": L("Rettungsbonus: Kein einziges Protokoll ist verloren gegangen."),
        },
        "kurpark": {
            "open": L("Ein Unwetter über dem Kurpark! Bäume krachen, und mittendrin sitzen eingeschlossene Besucher fest. Ich höre ihre Angst — und die der Tiere. Halt die Wege frei, damit ihnen nichts geschieht!"),
            "anecdote": L("Der Kurpark war immer der Stolz von Königstein — Kurkonzerte, Sonntagsspaziergänge, verliebte Paare unter den alten Bäumen. Heute peitscht der Sturm Funken über die Wege. Bring die Menschen sicher zum Kurhaus, so wie es unsere Wehr seit jeher tut."),
            "hint": L("Der Sturm treibt allerlei Feuer über die Wege — halt die Besucher frei! ABC-Pulver ist dein Allrounder für Holz, Flüssiges und Strom. Aber die Fritteuse vom Imbiss und der Strom: niemals Wasser, und der Fettbrand will seinen eigenen Löscher."),
            "close": L("Der Sturm zieht ab, und alle Besucher sind wohlauf im Kurhaus. Dieses stille Dankeschön in ihren Augen — dafür lohnt sich alles. Zusammen sind wir stark, mein Freund."),
            "bonus": L("Rettungsbonus: Alle eingeschlossenen Besucher sind in Sicherheit."),
        },
        "feuerwerk": {
            "open": L("Das Jubiläumsfest! Und ausgerechnet jetzt kippt ein Feuerwerkskörper um und droht die Bühne zu entzünden. Ich liebe dieses Fest so sehr — bitte, rette die Bühne!"),
            "anecdote": L("150 Jahre Freiwillige Feuerwehr Königstein — heute feiert die ganze Stadt. Neben der Bühne stehen Sprit für die Effekte, Kabel für die Lichter und ein E-Scooter-Akku am Ladepunkt. Ein Funke genügt. Aber wenn eine Gemeinschaft zusammensteht, fürchte selbst ich mich weniger."),
            "hint": L("Am Bühnenrand mischen sich Sprit, Kabel und ein glühender Akku — ein heikles Trio! CO₂ bändigt Sprit und Kabel, sauber und ohne Rückstände. Den Akku zähmt nur das Metallbrandpulver; niemals Wasser hier."),
            "close": L("Die Bühne steht, das Feuerwerk ist entschärft, und das Fest geht weiter! Sieh nur, wie alle zusammenhalten. Vielleicht … vielleicht bin ich ja doch ein kleiner Feuerwehrgeist. Danke, dass du an Königstein glaubst."),
            "bonus": L("Rettungsbonus: Bühne und Festgäste sind unversehrt."),
        },
    },
    # --- Anton's growth arc (ITEM-028) -------------------------------------------
    # His courage as the campaign progresses, indexed by the number of story missions
    # completed (0..4). Shown as a small mood line; his drawn ghost also stands taller,
    # more solid and a touch brighter with each mission (in the browser).
    "arc": {
        "courage": [
            L("Ich bin nur ein scheuer Burggeist … aber ich versuche, mutig zu sein. Bleib bei mir."),
            L("Schon ein Einsatz geschafft — mein altes Geisterherz klopft ein bisschen mutiger."),
            L("Zwei Einsätze! Weißt du, langsam traue ich mich sogar näher ans Feuer heran."),
            L("Drei gemeistert — ich flüstere nicht mehr nur, ich rufe fast schon Kommandos!"),
            L("Alle Einsätze gemeistert. Ich stehe aufrecht und stolz — fast wie ein echter Feuerwehrgeist."),
        ],
    },
    # --- Between-mission reward vignettes (ITEM-028) -----------------------------
    # DECISION (Adam): gentle, FICTIONAL, animated scenes — no real names, no dated
    # real events. They evoke the brigade's 150-year spirit (courage, helping
    # neighbours, the town through the years) without claiming specific real people.
    # "scene" names a lightweight canvas animation drawn in the browser. Keyed by
    # mission key. The library vignette carries the "finds his own name" beat.
    "vignettes": {
        "fachwerk": {
            "title": L("Nachbarn in der Nacht"),
            "scene": "lantern",
            "caption": L("Vor langer Zeit, so erzählt man sich, reichten sich Nachbarn in einer engen Gasse eimerweise Wasser weiter, bis der letzte Funke erlosch. Kein Name ist geblieben — nur der Mut, füreinander dazustehen."),
        },
        "bibliothek": {
            "title": L("Ein Name im Protokoll"),
            "scene": "records",
            "caption": L("Zwischen den vergilbten Zeilen entdeckt Anton eine Eintragung, die klingt wie sein eigener Name. „Da … das könnte ich sein.“ Zum ersten Mal seit 150 Jahren fühlt er sich wahrhaftig gesehen."),
        },
        "kurpark": {
            "title": L("Nach dem Sturm"),
            "scene": "storm",
            "caption": L("Als das Unwetter sich legte, standen die Menschen im Kurpark noch lange beieinander — durchnässt, erleichtert, dankbar. So war es wohl schon immer: Gemeinschaft hält jedem Sturm stand."),
        },
        "feuerwerk": {
            "title": L("150 Jahre Licht"),
            "scene": "festival",
            "caption": L("Über der Festbühne steigen Funken in den Nachthimmel. Anderthalb Jahrhunderte lang hat diese Stadt zusammengehalten — und Anton ist bei jedem Fest, jeder Sorge, jedem Jubel mitgeschwebt."),
        },
    },
    # --- The finale (ITEM-028) ---------------------------------------------------
    # Plays once, when ALL four missions are complete: the community gives Anton a
    # little fire helmet (he wears it from now on) and the closing message lands in
    # plain words — courage, compassion and community matter more than any equipment.
    "finale": {
        "title": L("Zum Feuerwehrgeist ernannt"),
        "scene": "helmet",
        "caption": L("Die ganze Gemeinschaft versammelt sich und setzt Anton eine kleine Feuerwehrmütze auf."),
        "lines": [
            L("Anton, du hast keinen Schlauch gehalten und keinen Tropfen Wasser berührt — und doch warst du bei jedem Einsatz dabei."),
            L("Du hast gewittert, gewarnt, Mut gemacht und Menschen verbunden. Genau das macht einen Feuerwehrgeist aus."),
            L("Mut, Mitgefühl und Zusammenhalt zählen mehr als jede Ausrüstung. Die Mütze ist nur das Zeichen für das, was du längst bist."),
            L("Zum Einsatz, VOR! — von nun an für immer als Feuerwehrgeist von Königstein."),
        ],
    },
}


def anton_de(path: tuple) -> str:
    """Read one of Anton's German lines by its path in ANTON, e.g.
    anton_de(("missions", "fachwerk", "open")). Returns '' if not present, so a
    missing line can never crash a render."""
    node = ANTON
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return ""
        node = node[key]
    return node.get("de", "") if isinstance(node, dict) else ""


def mission_lines_de(key: str) -> dict:
    """Anton's per-mission framing (open/anecdote/hint/close/bonus) as plain German
    strings for the browser. Empty dict if the mission has no framing."""
    m = ANTON["missions"].get(key)
    if not m:
        return {}
    return {field: line.get("de", "") for field, line in m.items()}


def vignette_de(key: str) -> dict:
    """A mission's reward vignette (ITEM-028): {title, scene, caption} in German, or
    {} if none. 'scene' is a lightweight canvas-animation id the browser draws."""
    v = ANTON.get("vignettes", {}).get(key)
    if not v:
        return {}
    return {"title": v["title"]["de"], "scene": v["scene"], "caption": v["caption"]["de"]}


def anton_arc_de() -> list:
    """Anton's courage lines by missions-completed (0..N), German (ITEM-028)."""
    return [line["de"] for line in ANTON.get("arc", {}).get("courage", [])]


def finale_de() -> dict:
    """The campaign finale (ITEM-028): {title, scene, caption, lines[]} in German."""
    f = ANTON.get("finale", {})
    if not f:
        return {}
    return {
        "title": f.get("title", {}).get("de", ""),
        "scene": f.get("scene", ""),
        "caption": f.get("caption", {}).get("de", ""),
        "lines": [line["de"] for line in f.get("lines", [])],
    }


# Backward-compatible views onto the single ANTON store, so the rest of the code
# (and the existing tests) keep using the same names while the text lives in one
# place. DANGER_REASONS is keyed by (class_id, tool_id) as before.
DANGER_REASONS = {
    tuple(k.split("|")): v["de"] for k, v in ANTON["danger_reasons"].items()
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

# Anton's "meet the fire" explanations (ITEM-011). A backward-compatible view onto
# the single ANTON store above (the text lives there, edited in one place).
CLASS_CARDS = {cid: line["de"] for cid, line in ANTON["class_cards"].items()}


# --- Supply-hazard mechanic (ITEM-016) ---------------------------------------
# Some fires can't just be sprayed — the supply feeding them must be cut off first.
# A level opts in via "supplies": ["gas", "power"]. In such a level, spraying that
# kind of fire while its supply is on does nothing (Anton says cut the supply first);
# cutting the supply puts those fires out. Level 1 declares no supplies, so it keeps
# its original "use the right extinguisher" behaviour for electrical fires.
HAZARD_CLASS = {"gas": "C", "power": "electrical"}
HAZARD_ACTION_DE = {"gas": "Gaszufuhr absperren", "power": "Strom abschalten"}
HAZARD_BUTTON_DE = {"gas": "🔧 Gas absperren", "power": "⚡ Strom abschalten"}
HAZARD_WARN_DE = {h: line["de"] for h, line in ANTON["hazard_warn"].items()}


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
        why = DANGER_REASONS.get((class_id, tool_id)) or anton_de(("feedback", "danger_fallback"))
        return why + (anton_de(("feedback", "danger_suffix")).format(tool=right) if right else "")
    if outcome == "useless":
        base = anton_de(("feedback", "useless"))
        return base + (anton_de(("feedback", "useless_suffix")).format(tool=right) if right else "")
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


# Distinctive German substrings that name each tool, used to guard Anton's free
# prose (ITEM-026). "metal" is checked before "powder" and its matches are blanked
# out first, because "Pulver" is a substring of "Metallbrandpulver". Wet chemical is
# matched only as the full extinguisher name, so the fire word "Fettbrand" never
# counts as naming the tool.
TOOL_KEYWORDS = [
    ("co2", ["CO₂", "Kohlendioxid"]),
    ("wetchem", ["Fettbrandlöscher"]),
    ("foam", ["Schaum"]),
    ("water", ["Wasser"]),
    ("metal", ["Metallbrandpulver", "Metallpulver", "Metallbrand"]),
    ("powder", ["ABC-Pulver", "Pulver"]),
]
# German negation cues: a hint clause that names a tool alongside one of these is a
# warning ("never water"), not a recommendation to use it.
NEGATION_CUES = ["kein", "nie", "nicht", "ohne", "statt", "weg von"]


def check_narration() -> tuple[bool, list]:
    """Guard Anton's free prose (ITEM-026). The fire-tool matrix is already checked
    against the reference; his anecdotes and hints are prose the matrix can't cover.

    The rule: a mission's in-play HINT must never name a tool that is DANGEROUS on one
    of that mission's fires as the thing to USE. A tool named in a hint clause that has
    no negation cue is treated as a recommendation and must be (a) a correct ('good')
    tool for at least one of the mission's fire classes and (b) never 'danger' for any
    of them. Dangerous tools may still appear in the hint under a warning ("nie Wasser").
    Framework-free, so it runs with --check-content."""
    problems: list[str] = []
    import re

    for lv in LEVELS:
        if not lv.get("campaign"):
            continue
        key = lv.get("key", "")
        hint = anton_de(("missions", key, "hint"))
        if not hint:
            problems.append(f"Campaign mission '{key}' is missing Anton's in-play hint.")
            continue
        classes = set()
        for w in lv.get("waves", []):
            classes.update(w.get("fires", []))
        danger_tools = {tid for cid in classes for tid in (t["id"] for t in TOOLS)
                        if MATRIX.get(cid, {}).get(tid) == "danger"}
        good_tools = {tid for cid in classes for tid in (t["id"] for t in TOOLS)
                      if MATRIX.get(cid, {}).get(tid) == "good"}

        # Split into small clauses so a warning cue only excuses its own clause.
        for clause in re.split(r"[,.;:!?—\n]", hint):
            if not clause.strip():
                continue
            negated = any(cue in clause.lower() for cue in NEGATION_CUES)
            work = clause
            for tid, keywords in TOOL_KEYWORDS:
                named = any(kw in work for kw in keywords)
                if not named:
                    continue
                # Blank this tool's matched words so later tools (e.g. "Pulver" inside
                # "Metallbrandpulver") don't get a false positive.
                for kw in keywords:
                    work = work.replace(kw, " ")
                if negated:
                    continue  # a warning, not a recommendation — allowed
                if tid in danger_tools:
                    problems.append(
                        f"Mission '{key}' hint recommends {tid}, which is DANGEROUS on one "
                        f"of this mission's fires — Anton must never point to a dangerous tool. "
                        f"Clause: \"{clause.strip()}\""
                    )
                elif tid not in good_tools:
                    problems.append(
                        f"Mission '{key}' hint recommends {tid}, which is not a correct tool "
                        f"for any of this mission's fires. Clause: \"{clause.strip()}\""
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
    start, then reports the recap. Deterministic.

    ITEM-040 note: `placements` is treated as a standing order — "keep this spot
    holding this tool" — not a one-time shopping list. A tower's charge runs out
    over a long level, so a safe player notices the empty spot and re-buys the same
    tool there; this loop does the same, every tick, for as long as the budget
    allows. This is what lets a correct, safe strategy always refill/replace in
    time and win — it never helps an UNSAFE tool, because a tool that never
    extinguishes anything never earns the budget back to keep re-buying."""
    st = GameState(level)
    st.status = "playing"
    for hazard in cut:
        st.shut_off(hazard)
    t = 0.0
    while st.status == "playing" and t < 180:
        for spot_index, tool_id in placements:
            if not any(tw["spot_index"] == spot_index for tw in st.towers):
                st.place_tower(spot_index, tool_id)
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

    # --- ITEM-017 guardrail: no single wrong tool can beat ANY level. Spamming one
    #     extinguisher on every build spot (and never cutting a supply) must lose every
    #     level — the core promise that you can only win by playing safe.
    tool_ids = [t["id"] for t in TOOLS]
    for i, lvl in enumerate(LEVELS):
        spots = len(lvl.get("build_spots", []))
        for tool in tool_ids:
            r = _play_out(lvl, [(s, tool) for s in range(spots)])
            if r["status"] == "won":
                problems.append(
                    f"Level {i + 1} ('{lvl['name']}') can be won by spamming a single "
                    f"tool ({tool}) — an unsafe/lazy strategy should never beat a level."
                )

    # --- ITEM-017: the second level (Kurpark) is won by a correct mix. ---
    if len(LEVELS) > 1:
        r = _play_out(LEVELS[1], [(0, "powder"), (2, "wetchem")])
        if r["status"] != "won" or r["leaked"] != 0:
            problems.append(
                "The second level should be won by a correct mix (powder + wet-chemical) "
                f"with nothing leaking, but got status={r['status']}, {r['leaked']} leaked."
            )

    # --- ITEM-027: each NEW story mission is only won by safe, correct play. ------
    # For every campaign mission we assert: (1) the intended correct play wins with
    # nothing leaking, (2) doing nothing loses, and (3) an all-water defence loses.
    # No single lazy tool can win any level — that is proved for ALL levels (new ones
    # included) by the ITEM-017 loop above, so it isn't repeated here.
    #
    # correct_play maps a mission key to (placements, supplies-to-cut):
    #   bibliothek: CUT THE POWER (clean, no water on the records) + water on the
    #               burning books (Class A). Water on the live wiring is wrong.
    #   feuerwerk:  CO₂ on the fuel + wiring (B/electrical) + metal powder on the battery (D).
    correct_play = {
        "bibliothek": ([(0, "water"), (2, "water")], ("power",)),
        "feuerwerk": ([(0, "co2"), (1, "metal")], ()),
    }
    for key, (placements, cut) in correct_play.items():
        lv = level_by_key(key)
        if lv is None:
            problems.append(f"Campaign mission '{key}' is missing.")
            continue
        r = _play_out(lv, placements, cut=cut)
        if r["status"] != "won" or r["leaked"] != 0:
            problems.append(
                f"Mission '{key}' should be won by the correct actions with nothing leaking, "
                f"but got status={r['status']}, {r['leaked']} leaked."
            )
        if _play_out(lv, [])["status"] != "lost":
            problems.append(f"Doing nothing should lose mission '{key}', but it didn't.")
        n = len(lv.get("build_spots", []))
        # All-water with NO supply cut (the lazy/unsafe case) must lose. For the
        # library this also proves you can't skip cutting the power.
        if _play_out(lv, [(i, "water") for i in range(n)])["status"] != "lost":
            problems.append(
                f"An all-water defence should lose mission '{key}' (water is dangerous there), "
                "but it didn't."
            )

    # --- ITEM-026: Anton's mission hints never point to a dangerous tool. ---------
    ok_narr, narr_problems = check_narration()
    if not ok_narr:
        problems.extend(narr_problems)

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
    (ITEM-001), plain canvas + JavaScript inside the one app (ITEM-003).

    The page is assembled from three editable source files — templates/index.html
    (the markup), static/styles.css, and static/game.js — with the CSS and JS
    inlined back into the single document at the markers below. The served bytes are
    identical to the old one-string version, so nothing needs a running server to be
    checked: the tests call this directly."""
    return _assemble_game_html()


# Where the page's source lives, resolved next to this script so it works unchanged
# on a laptop or a hosting server (uvicorn's working directory doesn't matter).
_TEMPLATE_PATH = os.path.join(HERE, "templates", "index.html")
_STYLES_PATH = os.path.join(HERE, "static", "styles.css")
_GAME_JS_PATH = os.path.join(HERE, "static", "game.js")

# Markers in templates/index.html (inside its own <style>/<script> tags) where the
# CSS and JS bodies are inlined back in. Kept in sync with how the files were split.
_STYLE_MARKER = "/*__FD_STYLES__*/"
_JS_MARKER = "//__FD_GAME_JS__"


@lru_cache(maxsize=1)
def _assemble_game_html() -> str:
    """Read the page template and inline its CSS and JS into one document. Cached
    once — the source files don't change while the app runs, and the tests call
    render_game_html() many times."""
    def _read(path: str) -> str:
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    html = _read(_TEMPLATE_PATH)
    html = html.replace(_STYLE_MARKER, _read(_STYLES_PATH))
    html = html.replace(_JS_MARKER, _read(_GAME_JS_PATH))
    return html


# --- Web app -----------------------------------------------------------------

@asynccontextmanager
async def _lifespan(_app):
    # The database builds itself on every start. On free hosting whose disk is
    # wiped between restarts (decided in ITEM-002), this is exactly what keeps the
    # app self-contained: nothing needs to be uploaded separately. (Uses the modern
    # "lifespan" startup hook rather than the deprecated on_event style.)
    init_db()
    yield


def build_app():
    """Create and return the FastAPI app with all its routes.

    FastAPI is imported here (not at module top level) so importing this module
    never requires the web framework — the game logic, the content check, and the
    safe-play simulator all run without it (ITEM-026/027 headless-testing unlock).
    The routes and their behaviour are identical to before; only their definition
    moved inside this function.
    """
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse

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

    @app.get("/api/anton")
    def api_anton() -> JSONResponse:
        """Anton's growth-arc courage lines and the campaign finale (ITEM-028).
        Fetched once by the browser; a fetch failure degrades gracefully there."""
        return JSONResponse({"courage": anton_arc_de(), "finale": finale_de()})

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

    return app


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
        ok3, p3 = check_narration()   # ITEM-026: guard Anton's mission hints
        if ok1 and ok2 and ok3:
            nc, nt = content_counts()
            print(f"Checks PASSED — {nc} Brandklassen, {nt} Löschmittel, "
                  f"{level_count()} Level, {len(campaign_missions())} Story-Missionen, "
                  f"Antons Hinweise geprüft, alle Prüfungen bestanden.")
            sys.exit(0)
        print("Checks FAILED:")
        for p in p1 + p2 + p3:
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
    app = build_app()
    print(f"Firefighter Defense läuft auf  http://{HOST}:{PORT}")
    print(f"Datenbank: {DATABASE_PATH}")
    uvicorn.run(app, host=HOST, port=PORT)
