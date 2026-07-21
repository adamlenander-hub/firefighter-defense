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
    /* --- ITEM-038 two-tone flat palette, as CSS variables (matches the approved
       mockup). body.hc overrides the SAME variables, so the high-contrast toggle
       (ITEM-020) keeps working for every element that uses them. --- */
    :root{
      color-scheme: light dark;
      --page:#f4f7fc; --ink:#1f2937; --muted:#5b6b7f;
      --red:#e4572e; --blue:#2f6fed; --panel:#ffffff; --line:#e4ebf5;
      --a:#f59e0b; --b:#8b5cf6; --c:#14b8a6; --e:#2f6fed; --d:#64748b; --f:#d6409f;
    }
    body.hc{
      --page:#0b0d12; --ink:#ffffff; --muted:#cbd5e1;
      --red:#ff7a4d; --blue:#7cb0ff; --panel:#161a22; --line:#39414f;
      --a:#ffc247; --b:#c4a7ff; --c:#4fe6cf; --e:#7cb0ff; --d:#c3cee0; --f:#ff86d3;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; padding: 1rem; min-height: 100vh;
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      background: var(--page); color: var(--ink);
      transition: background .2s, color .2s;
      display: flex; flex-direction: column; align-items: center; gap: .6rem;
    }
    header { text-align: center; }
    h1 { margin: 0; font-size: 1.35rem; color: var(--ink); }
    .place { margin: .15rem 0 0; color: var(--muted); font-size: .9rem; }
    .bar { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; justify-content: center; }
    /* ITEM-053 landscape-phone menus: the wrapper is a no-op outside the landscape
       media query below (display:contents removes its own box, so its children
       stay direct flex items of the STATUS .bar exactly as before — desktop and
       portrait layout are byte-identical to today). */
    #settingsGroup { display: contents; }
    /* The two menu buttons only exist visually inside the landscape media query;
       everywhere else they are hidden, so desktop/portrait never see them. */
    .menu-btn { display: none; }
    .lives { font-size: 1.1rem; display: none; }
    button {
      font: inherit; padding: .55rem 1.05rem; border-radius: 14px; cursor: pointer;
      border: none; background: var(--panel); color: var(--ink);
      box-shadow: 0 2px 0 var(--line); font-weight: 600;
      min-height: 44px;                 /* comfortable finger target (ITEM-020) */
    }
    button.active { background: var(--red); color: #fff; box-shadow: 0 3px 0 rgba(0,0,0,.15); }
    button:disabled { opacity: .5; cursor: default; }
    label { display: inline-flex; align-items: center; gap: .3rem; min-height: 44px; color: var(--muted); }
    label input { width: 20px; height: 20px; }
    /* ITEM-036 extinguisher palette cards: graphic + label + info affordance */
    .tool { display: inline-flex; flex-direction: column; align-items: stretch; gap: .2rem; }
    .toolbtn { display: flex; flex-direction: column; align-items: center; gap: .1rem; padding: .4rem .5rem; min-width: 70px; }
    .toolbtn canvas { display: block; }
    .toolbtn .tname { font-size: .74rem; font-weight: 700; }
    .toolbtn .tcost { font-size: .68rem; color: var(--muted); }
    .toolbtn.active .tcost { color: rgba(255,255,255,.9); }
    .toolinfo { min-height: 34px; padding: .15rem .5rem; font-size: .74rem; border-radius: 10px; box-shadow: 0 1px 0 var(--line); }
    .wrap { width: 100%; max-width: 960px; }
    canvas {
      width: 100%; height: auto; border-radius: 22px; box-shadow: 0 10px 30px rgba(31,41,55,.12);
      background: var(--panel); display:block;
      touch-action: manipulation;       /* reliable taps, no double-tap zoom delay */
    }
    .legend { display:flex; flex-wrap:wrap; gap:1rem; justify-content:center; color:var(--muted); font-size:.82rem; }
    .legend span::before { content:"● "; }
    .foot { color:var(--muted); font-size:.8rem; }
    #hint { color: var(--muted); }

    /* Large text in high-contrast so it reads across a room / on a projector
       (ITEM-020). Colours come from the body.hc variables above; this only bumps
       sizes and forces a plain dark board frame. */
    body.hc { font-size: 1.12rem; }
    body.hc canvas { border: 2px solid var(--line); box-shadow: none; }
    body.hc #hint, body.hc #feedback, body.hc .legend,
    body.hc .place, body.hc #antonMood, body.hc label { font-size: 1.05rem !important; }

    /* --- Portrait / small-screen: cap the board so the extinguisher palette and
       controls stay on-screen and reachable during play (ITEM-020). --- */
    @media (max-width: 720px) {
      body { padding: .5rem; }
      h1 { font-size: 1.12rem; }
      .wrap { max-width: 100%; }
      canvas { width:auto; max-width:100%; max-height:52vh; margin:0 auto; }
    }
    @media (orientation: portrait) and (max-width: 900px) {
      canvas { width:auto; max-width:100%; max-height:48vh; margin:0 auto; }
    }

    /* --- ITEM-053 landscape-phone layout (Option B: "menu"). Landscape PHONES are
       short (height <= 500px); a landscape desktop monitor is landscape but tall,
       so it never matches, and portrait never matches either — this block is fully
       additive and only takes effect on short landscape screens. Everything here
       only ADDS rules or overrides the two opt-in wrapper/buttons above; no existing
       rule outside this block is changed. --- */
    @media (orientation: landscape) and (max-height: 500px) {
      body { padding: .35rem; gap: .3rem; }
      .menu-btn { display: inline-flex; }

      /* Compact header: keep a slim title, hide the subtitle/place/mood lines. */
      header { line-height: 1.1; }
      h1 { font-size: .78rem; margin: 0; }
      header p { display: none; }

      /* Mission dropdown: reuses the existing #levelBar mission buttons — it just
         takes no space by default and becomes an anchored panel when opened. */
      #levelBar {
        position: absolute; top: 2.6rem; left: .35rem; display: none;
        background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
        box-shadow: 0 8px 24px rgba(31,41,55,.14); padding: .4rem; z-index: 30;
        max-width: 82vw; max-height: 70vh; overflow: auto;
      }
      #levelBar.dd-open { display: flex; flex-direction: column; align-items: stretch; }

      /* Settings dropdown: the wrapper becomes a real box again (undoing the
         display:contents above) and is positioned under the ⚙ button. */
      #settingsGroup {
        position: absolute; top: 2.6rem; right: .35rem; display: none;
        flex-direction: column; align-items: stretch; gap: .3rem; min-width: 200px;
        background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
        box-shadow: 0 8px 24px rgba(31,41,55,.14); padding: .5rem; z-index: 30;
      }
      #settingsGroup.dd-open { display: flex; }
      #settingsGroup label { min-height: 34px; }

      /* Compact one-row palette with a small corner ℹ badge instead of the "ℹ Info"
         button (DOM/text unchanged — only the badge's own text is hidden via
         font-size:0 and re-shown through the ::before pseudo-element). */
      #toolPalette { gap: .3rem; padding: 0; }
      .tool { position: relative; }
      .toolbtn { min-width: 56px; padding: .25rem .3rem; gap: 0; }
      .toolbtn canvas { width: 22px; height: 30px; }
      .toolbtn .tname { font-size: .62rem; }
      .toolbtn .tcost { font-size: .58rem; }
      .toolinfo {
        position: absolute; top: 2px; right: 2px; width: 16px; height: 16px;
        min-height: 0; min-width: 0; padding: 0; border-radius: 50%; font-size: 0;
        box-shadow: none; background: var(--line); color: var(--ink);
      }
      .toolinfo::before { content: "ℹ"; font-size: .62rem; }

      /* Single ellipsised hint line; the feedback line, legends and footer are not
         needed on a phone-landscape play screen. */
      #hint {
        display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        font-size: .68rem; max-width: 100%; margin: 0;
      }
      #feedback, .legend, #foot { display: none; }
      #hazardControls { gap: .3rem; padding: 0; }

      /* The board takes everything left over — no scrolling. */
      .wrap { max-width: 100%; }
      canvas { width: auto; max-width: 100%; max-height: calc(100dvh - 150px); margin: 0 auto; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Firefighter Defense — Königstein</h1>
    <p style="margin:.1rem 0; font-size:.85rem; color:var(--red); font-weight:600;">🚒 Freiwillige Feuerwehr Königstein im Taunus · 150 Jahre</p>
    <p class="place" id="place">Einsatz wird geladen …</p>
    <p id="antonMood" style="margin:.1rem 0 0; font-size:.82rem; font-style:italic; color:var(--muted);"></p>
  </header>

  <div class="bar" id="levelBar"></div>
  <div class="bar">
    <button id="missionMenuBtn" class="menu-btn" type="button" aria-expanded="false">🎯 Mission ▾</button>
    <span class="lives" id="lives"></span>
    <span id="budget" style="font-weight:600;"></span>
    <button id="startBtn">Einsatz starten</button>
    <span id="settingsGroup">
      <label style="font-size:.85rem;"><input type="checkbox" id="cardsToggle" checked> Antons Karten</label>
      <label style="font-size:.85rem;"><input type="checkbox" id="contrastToggle"> Große Schrift / Hoher Kontrast</label>
      <label style="font-size:.85rem;"><input type="checkbox" id="soundToggle" checked> Ton</label>
      <button id="libBtn">Antons Wissen</button>
    </span>
    <span id="info" style="color:var(--muted); font-size:.9rem;"></span>
    <button id="gearMenuBtn" class="menu-btn" type="button" aria-expanded="false">⚙</button>
  </div>

  <div class="bar" id="toolPalette"></div>
  <div class="bar" id="hazardControls"></div>
  <p class="foot" id="hint">Löscher wählen, dann auf einen blauen Bauplatz tippen. Der richtige Löscher löscht, der falsche wirkt nicht — ein gefährlicher lässt das Feuer auflodern. Löscher leeren sich (Anzeige am Turm) und müssen ersetzt werden. Falsch gebaut? Ohne gewählten Löscher auf den Turm tippen, um ihn abzubauen (keine Rückerstattung). Tastatur: 1–6 wählt den Löscher, Pfeiltasten wählen den Bauplatz, Enter setzt, Rücktaste/Entf baut ab, Leertaste startet.</p>
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
    <div style="background:var(--panel); color:var(--ink); max-width:26rem; margin:1rem; padding:1.4rem 1.6rem; border-radius:20px; text-align:center; box-shadow:0 20px 50px rgba(0,0,0,.35);">
      <div id="cardIcon" style="font-size:2.6rem;"></div>
      <h3 id="cardTitle" style="margin:.3rem 0;"></h3>
      <p id="cardText" style="line-height:1.5;"></p>
      <p style="font-size:.8rem; color:var(--muted); margin:.6rem 0;">— Anton, der Burggeist 👻</p>
      <button id="cardOk">Verstanden</button>
    </div>
  </div>

  <!-- End-of-level recap (ITEM-013) -->
  <div id="recap" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,.5); align-items:center; justify-content:center; z-index:11;">
    <div style="background:var(--panel); color:var(--ink); max-width:30rem; margin:1rem; padding:1.4rem 1.6rem; border-radius:20px; box-shadow:0 20px 50px rgba(0,0,0,.35);">
      <h2 id="recapTitle" style="margin:.2rem 0; text-align:center;"></h2>
      <p id="recapScore" style="text-align:center; font-size:1.15rem; font-weight:600; margin:.3rem 0;"></p>
      <p id="recapLine" style="text-align:center; color:var(--muted); margin:.2rem 0 .8rem;"></p>
      <p id="recapAnton" style="text-align:center; font-style:italic; color:var(--ink); margin:.2rem 0 .8rem; line-height:1.5;"></p>
      <div id="recapClasses" style="font-size:.9rem;"></div>
      <div style="text-align:center; margin-top:1rem; display:flex; gap:.5rem; justify-content:center; flex-wrap:wrap;">
        <button id="recapNext" class="active" style="display:none;">Nächster Einsatz ▶</button>
        <button id="recapAgain">Neu starten</button>
        <button id="recapLib">Antons Wissen</button>
      </div>
    </div>
  </div>

  <!-- Antons Wissen library (ITEM-014) -->
  <div id="lib" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,.5); align-items:center; justify-content:center; z-index:12;">
    <div style="background:var(--panel); color:var(--ink); max-width:34rem; max-height:86vh; overflow:auto; margin:1rem; padding:1.2rem 1.4rem; border-radius:20px; box-shadow:0 20px 50px rgba(0,0,0,.35);">
      <h2 style="margin:.2rem 0; text-align:center;">Antons Wissen 👻</h2>
      <p style="text-align:center; color:var(--muted); margin:.2rem 0 .8rem;">Welcher Löscher passt zu welchem Feuer?</p>
      <div id="libBody" style="font-size:.9rem;"></div>
      <div style="text-align:center; margin-top:1rem;"><button id="libClose">Schließen</button></div>
    </div>
  </div>

  <!-- Tool info pop-up (ITEM-036) — the extinguisher graphic + its guarded facts -->
  <div id="toolInfo" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,.45); align-items:center; justify-content:center; z-index:12;">
    <div style="background:var(--panel); color:var(--ink); max-width:24rem; margin:1rem; padding:1.2rem 1.4rem; border-radius:20px; text-align:center; box-shadow:0 20px 50px rgba(0,0,0,.35);">
      <canvas id="tiCanvas" width="62" height="80" style="display:block; margin:0 auto .2rem;"></canvas>
      <h3 id="tiTitle" style="margin:.2rem 0;"></h3>
      <div id="tiBody" style="font-size:.92rem; text-align:left;"></div>
      <div style="text-align:center; margin-top:1rem;"><button id="tiClose">Schließen</button></div>
    </div>
  </div>

  <!-- Reward vignette — a short animated scene after a mission win (ITEM-028) -->
  <div id="vignette" style="display:none; position:fixed; inset:0; background:rgba(20,10,5,.72); align-items:center; justify-content:center; z-index:13;">
    <div style="background:#1f1206; color:#fff7ed; max-width:32rem; margin:1rem; padding:1rem 1.2rem; border-radius:18px; box-shadow:0 20px 50px rgba(0,0,0,.5); text-align:center;">
      <h3 id="vigTitle" style="margin:.2rem 0; color:#fdba74;"></h3>
      <canvas id="vigCanvas" width="480" height="220" style="width:100%; height:auto; border-radius:12px; background:#0b0704; display:block; margin:.4rem 0;"></canvas>
      <p id="vigCaption" style="line-height:1.5; font-size:.95rem;"></p>
      <p style="font-size:.78rem; color:#c9a98f; margin:.4rem 0;">— Anton, der Burggeist 👻</p>
      <button id="vigClose" class="active">Weiter</button>
    </div>
  </div>

  <!-- One-time finale — the community gives Anton his helmet + closing message (ITEM-028) -->
  <div id="finale" style="display:none; position:fixed; inset:0; background:rgba(10,6,20,.85); align-items:center; justify-content:center; z-index:14;">
    <div style="background:#160f23; color:#f5f3ff; max-width:34rem; max-height:92vh; overflow:auto; margin:1rem; padding:1.1rem 1.3rem; border-radius:18px; box-shadow:0 20px 60px rgba(0,0,0,.6); text-align:center;">
      <h2 id="finTitle" style="margin:.2rem 0; color:#fca5a5;"></h2>
      <canvas id="finCanvas" width="480" height="240" style="width:100%; height:auto; border-radius:12px; background:#0a0614; display:block; margin:.4rem 0;"></canvas>
      <p id="finCaption" style="font-style:italic; color:#ddd6fe; margin:.3rem 0;"></p>
      <div id="finLines" style="line-height:1.6; font-size:.98rem; text-align:left; margin:.4rem 0;"></div>
      <button id="finClose" class="active">Zum Fest 🎉</button>
    </div>
  </div>

  <script>
    // Dials — MUST match the server (GameState). The spawn schedule itself is sent
    // by the server (level.schedule), so it isn't rebuilt here.
    var FIRE_PX_PER_SEC = 90.0;
    var TOWER_RANGE = 130.0, TOWER_COOLDOWN = 0.7, EXTINGUISH_REWARD = 12;
    var SMART_BONUS = 6, DANGER_SPEEDUP = 0.10;
    // ITEM-041: fires resist being put out — see the Python FIRE_HP/*_HIT_DAMAGE
    // comment for the full rule (good = one hit, weak = two).
    var FIRE_HP = 1.0, GOOD_HIT_DAMAGE = 1.0, WEAK_HIT_DAMAGE = 0.55;
    // ITEM-040: extinguishers deplete — see the Python TOWER_CHARGE_BASE/
    // CAMPAIGN_CHARGE_FACTOR comment for the full rule (charge tightens mission by
    // mission; only a shot that actually discharges AT the fire — good/weak/danger,
    // never a fully-useless one — spends it).
    var TOWER_CHARGE_BASE = 8;
    var CAMPAIGN_CHARGE_FACTOR = {1: 1.0, 2: 0.85, 3: 0.7, 4: 0.55};
    var MIN_TOWER_CHARGE = 3;
    function towerChargeFor(lv){
      var factor = (lv && lv.mission && CAMPAIGN_CHARGE_FACTOR[lv.mission]) || 1.0;
      return Math.max(MIN_TOWER_CHARGE, Math.round(TOWER_CHARGE_BASE * factor));
    }
    // ITEM-034: caps how many fires can ever be alive at once, so a chain of water
    // splitting a liquid/cooking-oil fire in two can never make a level unwinnable.
    var MAX_ACTIVE_FIRES = 14;
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
    // --- Anton-as-narrator + campaign state (ITEM-026 / ITEM-027) ---
    var antonLines = {};    // the loaded level's per-mission framing (open/anecdote/hint/close/bonus)
    var missionKey = null;  // stable level key, e.g. 'fachwerk'
    var missionNo = null;   // story mission number (1..4), or null for the side/training level
    var isCampaign = false; // true for the four story missions
    var hintShown = false;  // Anton's single in-play whisper per game (calm pacing)
    var levelsMeta = [];    // /api/levels list, with campaign metadata
    var currentIndex = -1;  // index of the level currently loaded
    var campaignProgress = 0; // highest story mission completed (persisted in the browser)
    // Anton's growth arc + reward scenes (ITEM-028)
    var antonArc = [];        // courage lines by missions-completed
    var antonFinale = {};     // the finale payload (title/caption/lines/scene)
    var vigRAF = null;        // the reward-scene animation handle (so it can be cancelled)
    var vignetteThenFinale = false; // after this vignette, play the finale?
    // Tablet / accessibility (ITEM-020) — all additive, desktop mouse unchanged.
    var HIT_RADIUS = 42;      // build-spot tap/click hit radius in board coords (finger-friendly)
    var keyIndex = -1;        // keyboard-highlighted build spot (-1 = none chosen yet)
    var keyboardActive = false; // draw the keyboard focus ring once the keyboard is used
    var contrastEnabled = false; // large-text / high-contrast mode

    // --- Friendly sound effects (ITEM-019) -----------------------------------
    // Sounds are GENERATED in the browser with the Web Audio API — there are NO
    // audio files, so nothing can fail to load (option A from the analysis). The
    // firm project rule "an optional part must never crash the page" is honoured
    // the same way the storage code is: the API is checked ONCE, and every audio
    // call is wrapped in try/catch. If audio is unsupported or anything throws,
    // the game simply carries on in silence with nothing shown to the player.
    var soundEnabled = true;                 // player-facing mute toggle (default: sound ON)
    var _AudioCtor = (typeof window !== 'undefined') && (window.AudioContext || window.webkitAudioContext);
    var audioSupported = !!_AudioCtor;       // decided once; if false we stay silent forever
    var audioCtx = null;                     // created lazily on the first user gesture
    var _lastSoundAt = 0;                    // light throttle so many towers can't stack a harsh pile-up

    // Autoplay-safe: browsers block sound until the player interacts. This is called
    // from the "Einsatz starten" button (a real user gesture) so the first effects
    // actually play. Guarded — a failure here just means the game stays quiet.
    function initAudio(){
      if (!audioSupported || !soundEnabled) return;
      try {
        if (!audioCtx) audioCtx = new _AudioCtor();
        if (audioCtx.state === 'suspended' && audioCtx.resume) audioCtx.resume();
      } catch (e){ /* audio unavailable — continue silently */ }
    }

    // One short, soft tone with a quick fade in/out (no clicks, nothing grating).
    function playTone(freq, startAt, dur, type, peak){
      if (!audioCtx) return;
      try {
        var t0 = audioCtx.currentTime + (startAt || 0);
        var osc = audioCtx.createOscillator();
        var gain = audioCtx.createGain();
        osc.type = type || 'sine';
        osc.frequency.setValueAtTime(freq, t0);
        var vol = (peak == null ? 0.11 : peak);
        gain.gain.setValueAtTime(0.0001, t0);
        gain.gain.exponentialRampToValueAtTime(vol, t0 + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
        osc.connect(gain); gain.connect(audioCtx.destination);
        osc.start(t0); osc.stop(t0 + dur + 0.03);
      } catch (e){ /* never let a sound break the page */ }
    }

    // The single guarded entry point every effect goes through. Respects mute and
    // the one-time support check, keeps sounds short, and lightly throttles the
    // reactive cues (good/danger/useless) so a frame with several towers firing
    // can't stack into a grating burst. Win/lose motifs are one-off and bypass it.
    function playSound(kind){
      if (!soundEnabled || !audioSupported) return;
      try {
        if (!audioCtx) return;                       // engine not unlocked yet — stay silent
        if (audioCtx.state === 'suspended' && audioCtx.resume) audioCtx.resume();
        if (kind === 'good' || kind === 'danger' || kind === 'useless'){
          var now = (audioCtx.currentTime || 0) * 1000;
          if (now - _lastSoundAt < 110) return;      // collapse same-frame repeats
          _lastSoundAt = now;
        }
        switch (kind){
          case 'good':                               // warm rising two-note — a correct extinguish
            playTone(523.25, 0,    0.12, 'sine', 0.10);
            playTone(783.99, 0.09, 0.16, 'sine', 0.10);
            break;
          case 'danger':                             // low soft buzz — a dangerous / wrong tool
            playTone(150, 0, 0.22, 'sawtooth', 0.07);
            break;
          case 'useless':                            // small subtle blip — a tool that does nothing
            playTone(320, 0, 0.06, 'triangle', 0.045);
            break;
          case 'win':                                // short cheerful up-motif at level won
            playTone(523.25, 0,    0.12, 'sine', 0.10);
            playTone(659.25, 0.11, 0.12, 'sine', 0.10);
            playTone(783.99, 0.22, 0.22, 'sine', 0.11);
            break;
          case 'lose':                               // gentle falling two-note at level lost
            playTone(392.00, 0,    0.16, 'sine', 0.09);
            playTone(261.63, 0.15, 0.28, 'sine', 0.09);
            break;
        }
      } catch (e){ /* an audio failure must never break or freeze the page */ }
    }

    // Mute persistence — same guarded localStorage pattern as loadContrast/saveContrast;
    // a browser that blocks storage must never throw. Default is sound ON.
    function saveSound(on){ try { window.localStorage.setItem('fd_sound', on ? '1':'0'); } catch(e){} }
    function loadSound(){
      var on = true;
      try { var v = window.localStorage.getItem('fd_sound'); if (v !== null) on = (v === '1'); }
      catch (e){ on = true; }
      soundEnabled = on;
      var cb = document.getElementById('soundToggle'); if (cb) cb.checked = on;
    }

    // Progress is stored in the browser so the fixed play order survives a reload.
    // Storage is optional — a browser that blocks it must never crash the page.
    function loadProgress(){
      try { var v = window.localStorage.getItem('fd_campaign_progress');
            campaignProgress = v ? (parseInt(v,10)||0) : 0; }
      catch (e) { campaignProgress = 0; }
    }
    function saveProgress(){
      try { window.localStorage.setItem('fd_campaign_progress', String(campaignProgress)); }
      catch (e) { /* storage unavailable — keep progress in memory only */ }
    }
    // Mission N is playable once the mission before it is won (mission 1 always is).
    function missionUnlocked(n){ return n <= campaignProgress + 1; }
    // Start the campaign over: clear saved progress and return to the locked state
    // with only mission 1 available. Storage clearing is guarded so it can't throw.
    function resetProgress(){
      if (typeof window.confirm === 'function' &&
          !window.confirm('Kampagne wirklich von vorne beginnen? Der Fortschritt wird gelöscht.')) return;
      campaignProgress = 0;
      try { window.localStorage.removeItem('fd_campaign_progress'); } catch (e) { /* storage off — ignore */ }
      renderLevelBar();
      var camp=levelsMeta.filter(function(l){ return l.campaign && l.mission; })
                         .slice().sort(function(a,b){ return a.mission-b.mission; });
      loadLevel(camp.length ? camp[0].index : 0);
    }

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
    // --- ITEM-038 two-tone flat helpers (ported from the approved mockup) ------
    // Read a CSS variable (the flat palette), cached per theme so it's cheap per frame.
    var _cssv={}, _cssvKey='';
    function cssv(n){
      var key = contrastEnabled ? 'hc' : 'lt';
      if (key!==_cssvKey){ _cssv={}; _cssvKey=key; }
      if (_cssv[n]!==undefined) return _cssv[n];
      var v=''; try { v=getComputedStyle(document.body).getPropertyValue(n).trim(); } catch(e){ v=''; }
      _cssv[n]=v; return v;
    }
    // Mix a hex colour toward white (amt>0) or black (amt<0) — gives the 2nd flat tone.
    function shade(hex,amt){
      hex=(hex||'').replace('#',''); if(hex.length===3) hex=hex.split('').map(function(x){return x+x;}).join('');
      if(hex.length<6) return '#888';
      var r=parseInt(hex.substr(0,2),16), g=parseInt(hex.substr(2,2),16), b=parseInt(hex.substr(4,2),16);
      var t=amt<0?0:255, a=Math.abs(amt);
      r=Math.round(r+(t-r)*a); g=Math.round(g+(t-g)*a); b=Math.round(b+(t-b)*a);
      return 'rgb('+r+','+g+','+b+')';
    }
    // Rounded-rect path.
    function rr(c,x,y,w,h,r){ c.beginPath(); c.moveTo(x+r,y); c.arcTo(x+w,y,x+w,y+h,r); c.arcTo(x+w,y+h,x,y+h,r); c.arcTo(x,y+h,x,y,r); c.arcTo(x,y,x+w,y,r); c.closePath(); }
    // The ONE allowed background gradient (sky), computed ONCE per size/theme.
    var _skyGrad=null, _skyKey='';
    function skyGradient(w,h){
      var key=w+'x'+h+(contrastEnabled?'d':'l');
      if(key!==_skyKey){
        var g=ctx.createLinearGradient(0,0,0,h);
        if(contrastEnabled){ g.addColorStop(0,'#0b0d12'); g.addColorStop(1,'#161f2b'); }
        else { g.addColorStop(0,'#e6effb'); g.addColorStop(1,'#f6f9fd'); }
        _skyGrad=g; _skyKey=key;
      }
      return _skyGrad;
    }
    // A fire class -> its flat-palette colour (visual only; letter/icon unchanged).
    var _CLASS_VAR={A:'--a',B:'--b',C:'--c',electrical:'--e',D:'--d',F:'--f'};
    function classColour(cls){ return cssv(_CLASS_VAR[cls]||'') || (classMap[cls]&&classMap[cls].colour) || '#e4572e'; }
    function flameShape(c,s,sc){ c.beginPath(); c.moveTo(0,-s*sc);
      c.bezierCurveTo(s*0.9*sc,-s*0.5*sc, s*0.75*sc,s*0.7*sc, 0,s*sc);
      c.bezierCurveTo(-s*0.75*sc,s*0.7*sc, -s*0.9*sc,-s*0.5*sc, 0,-s*sc); c.closePath(); }
    // Two-tone flat extinguisher body in the tool colour. Takes a context so it can
    // be drawn on the board (towers) AND on the little palette canvases (ITEM-036).
    function drawExtShape(c,x,y,w,h,col){
      c.save();
      c.fillStyle=col; rr(c,x,y,w,h,w*0.36); c.fill();
      c.save(); rr(c,x,y,w,h,w*0.36); c.clip();
      c.fillStyle=shade(col,-0.22); c.fillRect(x+w*0.55,y,w*0.5,h);
      c.fillStyle=shade(col,0.35); c.fillRect(x,y,w*0.16,h);
      c.restore();
      c.fillStyle=cssv('--ink')||'#1f2937'; rr(c,x+w*0.32,y-h*0.14,w*0.36,h*0.14,3); c.fill();
      rr(c,x+w*0.12,y-h*0.05,w*0.76,h*0.09,3); c.fill();
      c.fillStyle='#ffffff'; rr(c,x+w*0.2,y+h*0.30,w*0.6,h*0.3,4); c.fill();
      c.restore();
    }
    // Tool colour, lightened in high-contrast so a dark tool still reads on a dark field.
    function toolColour(hex){ return contrastEnabled ? shade(hex||'#334155',0.4) : (hex||'#334155'); }

    function trace(wp) { ctx.beginPath(); ctx.moveTo(wp[0][0], wp[0][1]); for (var i=1;i<wp.length;i++) ctx.lineTo(wp[i][0],wp[i][1]); }
    // The shared two-tone rounded ribbon — the clear walking lane under every material.
    function drawRibbon(wp, road){
      ctx.lineCap='round'; ctx.lineJoin='round';
      ctx.strokeStyle=road; ctx.lineWidth=44; trace(wp); ctx.stroke();
      ctx.strokeStyle=shade(road,0.22); ctx.lineWidth=44; ctx.save(); ctx.translate(0,-7); trace(wp); ctx.stroke(); ctx.restore();
      ctx.strokeStyle=road; ctx.lineWidth=30; trace(wp); ctx.stroke();
    }
    // Unit tangent along the path at fraction t (for placing material motifs).
    function pathTangentAt(wp, t){
      var d=0.004, a=pathPointAt(wp, Math.max(0,t-d)), b=pathPointAt(wp, Math.min(1,t+d));
      var dx=b[0]-a[0], dy=b[1]-a[1], L=Math.hypot(dx,dy)||1; return [dx/L, dy/L];
    }
    // Evenly-spaced points along the path with a perpendicular (across-lane) vector.
    // Cached per level+spacing so it is computed ONCE, not per frame (performance).
    var _motifCache={};
    function pathMotifs(wp, spacing){
      var key=(level&&level.key||'')+'|'+spacing+'|'+wp.length;
      if (_motifCache[key]) return _motifCache[key];
      var total=pathLength(wp), n=Math.max(2, Math.floor(total/spacing)), arr=[];
      for (var i=0;i<=n;i++){ var t=i/n, p=pathPointAt(wp,t), tg=pathTangentAt(wp,t);
        arr.push({x:p[0], y:p[1], nx:-tg[1], ny:tg[0]}); }
      _motifCache[key]=arr; return arr;
    }
    // --- ITEM-044: per-mission path material (picked by the level's key) ---------
    // Each keeps the clear ribbon lane; the material is a themed overlay on top, and
    // every material function is high-contrast aware so the lane stays legible.
    function drawPathTimber(wp){                 // mission 1 — timber planks / boardwalk
      var hc=contrastEnabled; drawRibbon(wp, hc?'#4a3826':'#b98a5a');
      var plank=hc?'#6b5236':'#8a6238', edge=hc?'#241a10':shade(plank,-0.28);
      ctx.lineCap='butt';
      pathMotifs(wp,26).forEach(function(m){ var hw=16;
        ctx.strokeStyle=edge; ctx.lineWidth=7; ctx.beginPath(); ctx.moveTo(m.x-m.nx*hw,m.y-m.ny*hw); ctx.lineTo(m.x+m.nx*hw,m.y+m.ny*hw); ctx.stroke();
        ctx.strokeStyle=plank; ctx.lineWidth=4; ctx.beginPath(); ctx.moveTo(m.x-m.nx*hw,m.y-m.ny*hw); ctx.lineTo(m.x+m.nx*hw,m.y+m.ny*hw); ctx.stroke(); });
      ctx.lineCap='round';
    }
    function drawPathBooks(wp){                  // mission 2 — flat books lying scattered along the trail (ITEM-059)
      var hc=contrastEnabled; drawRibbon(wp, hc?'#2b3546':'#d9c9a8');
      var covers=hc?['#7cb0ff','#ffc247','#ff86d3','#4fe6cf','#c4b5fd']:['#2f6fed','#e4572e','#8b5cf6','#14b8a6','#d6a409'];
      // Stable pseudo-random per book index (NOT per frame) so the scatter holds still.
      function h(n){ var x=Math.sin(n*12.9898)*43758.5453; return x-Math.floor(x); }
      pathMotifs(wp,22).forEach(function(m,i){
        var col=covers[i%covers.length];
        var off=(h(i*2+1)-0.5)*20, along=(h(i*2+7)-0.5)*14;   // scatter across + a little along the lane
        var ang=(h(i*3+2)-0.5)*Math.PI;                        // any angle — haphazard, not aligned to the lane
        var bw=17+h(i+5)*7, bh=12+h(i+9)*5;                    // varied book size
        ctx.save();
        ctx.translate(m.x+m.nx*off+m.ny*along, m.y+m.ny*off-m.nx*along);
        ctx.rotate(ang);
        ctx.fillStyle=shade(col,-0.32); rr(ctx,-bw/2-1.5,-bh/2+2,bw,bh,2.5); ctx.fill();   // underside/shadow — books lie flat, face-up
        ctx.fillStyle=col; rr(ctx,-bw/2,-bh/2,bw,bh,2.5); ctx.fill();                        // cover
        ctx.fillStyle=shade(col,-0.4); ctx.fillRect(-bw/2,-bh/2,3.5,bh);                     // spine down the left edge
        ctx.fillStyle=hc?'#e5e7eb':'#fdfaf0'; ctx.fillRect(bw/2-3,-bh/2+2,2.5,bh-4);         // page block on the right edge
        ctx.strokeStyle=hc?'rgba(255,255,255,.55)':'rgba(255,255,255,.8)'; ctx.lineWidth=1.4; ctx.lineCap='round';
        ctx.beginPath(); ctx.moveTo(-bw/2+6,-bh*0.12); ctx.lineTo(bw/2-6,-bh*0.12); ctx.moveTo(-bw/2+6,bh*0.16); ctx.lineTo(bw/2-8,bh*0.16); ctx.stroke();  // title lines
        ctx.restore();
      });
    }
    function drawPathGravel(wp){                 // mission 3 — park gravel / earth trail
      var hc=contrastEnabled; drawRibbon(wp, hc?'#333e30':'#c9b48f');
      var g1=hc?'#5a674f':'#a8926b', g2=hc?'#414c3c':'#8f7a58';
      pathMotifs(wp,13).forEach(function(m,i){ var off=((i*37)%9-4);
        ctx.fillStyle=(i%2)?g1:g2; ctx.beginPath(); ctx.arc(m.x+m.nx*off, m.y+m.ny*off, (i%3)+1.6, 0, Math.PI*2); ctx.fill(); });
    }
    function drawPathChips(wp){                  // mission 4 — festival wood chips
      var hc=contrastEnabled; drawRibbon(wp, hc?'#3a2c1c':'#caa778');
      var c1=hc?'#7a5a38':'#a97e4e', c2=hc?'#5b4326':'#8a6238';
      pathMotifs(wp,15).forEach(function(m,i){ var off=((i*29)%11-5);
        ctx.save(); ctx.translate(m.x+m.nx*off, m.y+m.ny*off); ctx.rotate(i*1.3);
        ctx.fillStyle=(i%2)?c1:c2; rr(ctx,-4,-1.7,8,3.4,1.4); ctx.fill(); ctx.restore(); });
    }
    function drawPathCables(wp){                 // Schlosserei — cables + a gas line
      var hc=contrastEnabled; drawRibbon(wp, hc?'#20262f':'#b8c2cf');
      function line(off,col,wd){ ctx.strokeStyle=col; ctx.lineWidth=wd; ctx.lineCap='round';
        ctx.beginPath(); pathMotifs(wp,8).forEach(function(m,i){ var px=m.x+m.nx*off, py=m.y+m.ny*off; i?ctx.lineTo(px,py):ctx.moveTo(px,py); }); ctx.stroke(); }
      line(-8, hc?'#ff7a4d':'#e4572e', 3.5);     // red cable
      line(0,  hc?'#ffc247':'#d6a409', 3.5);     // yellow gas line
      line(8,  hc?'#7cb0ff':'#2f6fed', 3.5);     // blue cable
    }
    function drawPath(wp){
      var key=level&&level.key;
      if (key==='fachwerk')       drawPathTimber(wp);
      else if (key==='bibliothek')drawPathBooks(wp);
      else if (key==='kurpark')   drawPathGravel(wp);
      else if (key==='feuerwerk') drawPathChips(wp);
      else if (key==='schlosserei')drawPathCables(wp);
      else {                                     // generic fallback ribbon + centre line
        var road=contrastEnabled?'#2b3546':'#c3cfdd'; drawRibbon(wp, road);
        ctx.strokeStyle=shade(road, contrastEnabled?0.4:-0.08); ctx.lineWidth=3; ctx.setLineDash([12,14]); trace(wp); ctx.stroke(); ctx.setLineDash([]);
      }
    }
    function drawBuildSpot(x,y){
      // ITEM-056 (replaces ITEM-049): an open build spot is a solid black circle with
      // a white border, drawn the SAME in every mode (normal + high-contrast) so it
      // stands out against any mission background. Radius kept at 24. A thin outer
      // dark edge keeps the white border readable even on a near-white background.
      ctx.beginPath(); ctx.arc(x,y,24,0,Math.PI*2);
      ctx.fillStyle='#000000'; ctx.fill();
      ctx.lineWidth=3; ctx.strokeStyle='#ffffff'; ctx.stroke();
      ctx.lineWidth=1; ctx.strokeStyle='rgba(0,0,0,0.55)'; ctx.beginPath(); ctx.arc(x,y,25.5,0,Math.PI*2); ctx.stroke();
    }
    // A clear focus ring on the keyboard-highlighted build spot (ITEM-020), so a
    // keyboard player can always see where they are.
    function drawKeyHighlight(){
      if (!keyboardActive || !level || keyIndex<0 || keyIndex>=level.build_spots.length) return;
      var s=level.build_spots[keyIndex];
      var pulse=30 + Math.sin(performance.now()/220)*3;
      ctx.save();
      ctx.strokeStyle='#f59e0b'; ctx.lineWidth=4;
      ctx.beginPath(); ctx.arc(s[0],s[1],pulse,0,Math.PI*2); ctx.stroke();
      ctx.strokeStyle='#78350f'; ctx.lineWidth=1.5;
      ctx.beginPath(); ctx.arc(s[0],s[1],pulse+3,0,Math.PI*2); ctx.stroke();
      ctx.fillStyle='#b45309'; ctx.font='bold 12px system-ui'; ctx.textAlign='center';
      ctx.fillText('▶ Bauplatz ' + (keyIndex+1), s[0], s[1]-pulse-6);
      ctx.restore();
    }
    function drawStart(wp){
      var b=cssv('--blue')||'#2f6fed';
      ctx.fillStyle=shade(b,-0.15); ctx.beginPath(); ctx.arc(wp[0][0],wp[0][1],13,0,Math.PI*2); ctx.fill();
      ctx.fillStyle=b; ctx.beginPath(); ctx.arc(wp[0][0],wp[0][1],8,0,Math.PI*2); ctx.fill();
      ctx.fillStyle=cssv('--muted')||'#5b6b7f'; ctx.font='600 12px system-ui'; ctx.textAlign='center'; ctx.fillText('Start', wp[0][0], wp[0][1]-20);
    }
    // Two-tone flat house; KEEPS the red damage flash + the HTML lives display.
    // ITEM-033: how battered the building looks, driven by remaining lives (0 =
    // pristine .. 3 = smoking ruin). Presentation only — the lose condition itself
    // is still lives<=0 in advance(), completely unchanged.
    function buildingDamageStage(){
      if (!game || !game.level || !game.level.building) return 0;
      var start = game.level.building.lives || 1;
      var remainFrac = Math.max(0, game.lives) / start;
      if (remainFrac <= 0) return 3;
      if (remainFrac <= 0.4) return 2;
      if (remainFrac < 1) return 1;
      return 0;
    }
    // ITEM-058 house-fire helpers. Everything is greyscale/high-contrast safe: the
    // three damage stages are told apart by AMOUNT — size + number of flames, height
    // of the smoke column, and (at the ruin) a structural roof collapse — never by
    // hue alone. Flames flicker and smoke rises cheaply off performance.now(), and hc
    // forces bright flame fills, white smoke and black/white structure.
    function houseFlame(fx, baseY, s, ph, hc){            // one animated flame, base anchored, rising up
      var flick = 0.5+0.5*Math.sin(performance.now()*0.006 + ph);
      ctx.save();
      ctx.translate(fx, baseY - s);
      var lean = (flick-0.5)*0.5;
      ctx.transform(1,0,lean,1,-lean*s,0);               // sway anchored at the base (y=+s)
      ctx.globalAlpha = 0.9;
      ctx.fillStyle = hc?'#ffb703':'#f97316';            // outer flame
      flameShape(ctx, s, 1 + flick*0.08); ctx.fill();
      ctx.save(); ctx.translate(0, s*0.22);
      ctx.fillStyle = hc?'#fff3b0':'#fbbf24';            // hot inner core
      flameShape(ctx, s*0.9, 0.5 + flick*0.22); ctx.fill(); ctx.restore();
      ctx.globalAlpha = 1;
      ctx.restore();
    }
    function housePlume(cx, topY, hc, count, spread, height){   // rising smoke column
      var now=performance.now()*0.001;
      ctx.save(); ctx.fillStyle = hc?'rgba(255,255,255,.6)':'rgba(64,64,64,.5)';
      for (var i=0;i<count;i++){
        var p=((now*0.3 + i/count)%1);
        var sx=cx + Math.sin(now*0.8 + i*1.3)*spread*(0.4+p);
        var sy=topY - p*height;
        ctx.globalAlpha = Math.max(0, 0.6*(1-p*0.9));
        ctx.beginPath(); ctx.arc(sx, sy, 5 + height*0.22*p, 0, Math.PI*2); ctx.fill();
      }
      ctx.globalAlpha = 1; ctx.restore();
    }
    function houseEmbers(cx, baseY, hc, spread, n){       // glowing embers drifting up
      var now=performance.now()*0.001;
      ctx.save();
      for (var i=0;i<n;i++){
        var p=((now*1.0 + i*0.41)%1);
        var ex=cx + Math.sin(now*3 + i*2.1)*spread;
        var ey=baseY - p*44;
        ctx.globalAlpha = Math.max(0,1-p);
        ctx.fillStyle = hc?'#ffffff':'#fde047';
        ctx.beginPath(); ctx.arc(ex, ey, 1.4 + 1.6*(1-p), 0, Math.PI*2); ctx.fill();
      }
      ctx.globalAlpha = 1; ctx.restore();
    }
    function houseScorch(x,bodyY,W,bodyH,hc,intensity){   // soot scorching up the walls
      ctx.save(); ctx.globalAlpha=(hc?0.5:0.32)*intensity; ctx.fillStyle = hc?'#000':'#1c1c1c';
      for (var i=0;i<4;i++){
        var sx=x+W*(0.14+i*0.24);
        ctx.beginPath(); ctx.moveTo(sx-7,bodyY+bodyH*0.2); ctx.quadraticCurveTo(sx-2,bodyY-10,sx+8,bodyY-24);
        ctx.lineTo(sx+2,bodyY-24); ctx.quadraticCurveTo(sx-7,bodyY-2,sx,bodyY+bodyH*0.2); ctx.closePath(); ctx.fill();
      }
      ctx.restore();
    }
    // The staged fire/ruin overlay, drawn on top of the (degraded) house.
    function drawHouseDamage(stage,x,bodyY,W,bodyH,yTop,bx,hc){
      houseScorch(x,bodyY,W,bodyH,hc, stage>=2?1:0.7);
      if (stage===1){                                     // a real, serious fire: several big flames + a tall window flame + a big plume
        houseFlame(x+W*0.24, bodyY+2,  bodyH*0.46, 0.6, hc);   // left roof
        houseFlame(x+W*0.52, yTop+4,   bodyH*0.52, 1.9, hc);   // near the apex
        houseFlame(x+W*0.76, bodyY+2,  bodyH*0.48, 0.0, hc);   // right roof
        houseFlame(x+21,     bodyY+30, bodyH*0.40, 1.1, hc);   // window, tall
        housePlume(bx+6, yTop-6, hc, 7, 15, 78);
        houseEmbers(bx, bodyY, hc, W*0.4, 5);
      } else if (stage===2){                              // fully engulfed: many huge flames swallowing the house, thick smoke, embers
        houseFlame(x+W*0.14, bodyY+4,  bodyH*0.56, 0.3, hc);
        houseFlame(x+W*0.34, yTop-2,   bodyH*0.64, 1.7, hc);   // over the roof
        houseFlame(x+W*0.52, yTop+2,   bodyH*0.70, 3.1, hc);   // apex, tallest
        houseFlame(x+W*0.70, yTop-2,   bodyH*0.64, 4.5, hc);
        houseFlame(x+W*0.88, bodyY+4,  bodyH*0.56, 5.6, hc);
        houseFlame(x+21,     bodyY+30, bodyH*0.50, 3.4, hc);   // blown-out window
        houseFlame(bx,       bodyY+bodyH*0.5, bodyH*0.46, 4.2, hc);   // door
        housePlume(bx, yTop-8, hc, 10, 22, 104);
        houseEmbers(bx, bodyY, hc, W*0.6, 14);
      } else if (stage>=3){                               // smoking ruin: burned out, no active fire — a big billowing smoke column dominates
        housePlume(bx-6, bodyY-6, hc, 14, 26, 150);
        houseEmbers(bx, bodyY+bodyH*0.55, hc, W*0.4, 4);      // a few faint dim smoulders
      }
    }
    function drawBuilding(b){
      var flashing = game && performance.now() < game.flashUntil;
      var hc=contrastEnabled;
      var stage = buildingDamageStage();
      var cream = flashing ? (hc?'#7a2b1e':'#f2b0a0') : (hc?'#e9d9b8':'#f3e4c2');
      if (stage>=3) cream = hc?'#2b2f36':'#3a352e';        // charred, near-black walls
      else if (stage===2) cream = shade(cream,-0.18);      // heavily scorched
      else if (stage===1) cream = shade(cream,-0.08);      // singed
      var W=94, H=76, x=b.x-W/2, yTop=b.y-H/2;
      var bodyY=yTop+18, bodyH=H-18;
      // body — TONE1 + a TONE2 shadow plane on the right third
      ctx.fillStyle=cream; rr(ctx,x,bodyY,W,bodyH,12); ctx.fill();
      ctx.save(); rr(ctx,x,bodyY,W,bodyH,12); ctx.clip(); ctx.fillStyle=shade(cream,-0.12); ctx.fillRect(x+W*0.66,bodyY,W*0.34,bodyH); ctx.restore();
      // ruin: a jagged structural crack splitting the charred body
      if (stage>=3){
        ctx.save(); ctx.strokeStyle=hc?'#000':'#141414'; ctx.lineWidth=2.5; ctx.lineJoin='round';
        ctx.beginPath(); ctx.moveTo(x+W*0.42,bodyY); ctx.lineTo(x+W*0.52,bodyY+bodyH*0.38); ctx.lineTo(x+W*0.44,bodyY+bodyH*0.68); ctx.lineTo(x+W*0.52,bodyY+bodyH); ctx.stroke();
        ctx.restore();
      }
      // roof — intact red triangle (bright on damage flash) until the ruin, when it COLLAPSES into a broken slump
      var red = flashing ? (hc?'#ff5a4d':'#dc2626') : (cssv('--red')||'#e4572e');
      if (stage>=3){
        red = hc?'#26282d':'#2a2621';                      // burnt-out, no more red
        ctx.fillStyle=red; ctx.beginPath();
        ctx.moveTo(x-6,bodyY+4);
        ctx.lineTo(x+W*0.20,bodyY-6); ctx.lineTo(x+W*0.34,bodyY+9);
        ctx.lineTo(x+W*0.52,bodyY-8); ctx.lineTo(x+W*0.68,bodyY+11);
        ctx.lineTo(x+W*0.86,bodyY-2); ctx.lineTo(x+W+6,bodyY+4);
        ctx.closePath(); ctx.fill();
      } else {
        if (stage>=1) red = shade(red,-0.16*stage);        // roof scorches as it burns
        ctx.fillStyle=red; ctx.beginPath(); ctx.moveTo(x-6,bodyY+4); ctx.lineTo(x+W/2,yTop-8); ctx.lineTo(x+W+6,bodyY+4); ctx.closePath(); ctx.fill();
        ctx.fillStyle=shade(red,-0.2); ctx.fillRect(x-6,bodyY,W+12,6);
      }
      // door + window — two-tone blue (dark/unlit as a ruin; window blown out once badly ablaze)
      var blue=cssv('--blue')||'#2f6fed', lit = stage<3;
      ctx.fillStyle=shade(blue,-0.15); rr(ctx,x+W/2-14,bodyY+18,28,bodyH-18,6); ctx.fill();
      ctx.fillStyle= lit ? blue : shade(blue,-0.5); rr(ctx,x+W/2-10,bodyY+22,20,bodyH-22,4); ctx.fill();
      if (stage>=2){                                       // blown-out window: dark hole + jagged glass shards
        ctx.fillStyle= hc?'#000':'#160f06'; rr(ctx,x+12,bodyY+12,18,18,4); ctx.fill();
        ctx.strokeStyle= hc?'#fff':'#4a3720'; ctx.lineWidth=1.4;
        ctx.beginPath();
        ctx.moveTo(x+12,bodyY+12); ctx.lineTo(x+20,bodyY+21); ctx.lineTo(x+14,bodyY+30);
        ctx.moveTo(x+30,bodyY+13); ctx.lineTo(x+22,bodyY+22); ctx.lineTo(x+28,bodyY+30);
        ctx.stroke();
      } else {
        ctx.fillStyle= shade(blue,0.55); rr(ctx,x+12,bodyY+12,18,18,4); ctx.fill();
      }
      // name label
      ctx.fillStyle=cssv('--ink')||'#1f2937'; ctx.font='700 13px system-ui'; ctx.textAlign='center';
      ctx.fillText(b.name_de||'Gebäude', b.x, bodyY+bodyH+16);
      // ITEM-058: the dramatic staged fire/ruin overlay itself
      if (stage>=1) drawHouseDamage(stage,x,bodyY,W,bodyH,yTop,b.x,hc);
    }
    // --- ITEM-039: distinctive animated fire characters, one per class ----------
    // Each fire is a bigger evil-faced character whose SHAPE + idle animation reflect
    // its type, drawn on top of the ITEM-038 two-tone flame + palette. The class
    // LETTER badge + emoji icon + reaction-ring shapes are KEPT exactly (greyscale-
    // and high-contrast-safe, ITEM-008) — the character art is decoration, never a
    // replacement. Animation is cheap sin/time off the render clock, with a per-fire
    // phase so a crowd doesn't pulse in lockstep. No fire fact / balance touched.
    function drawEvilFace(c, s, sparkEyes, tt, ph){
      c.fillStyle='#fff';
      c.beginPath(); c.arc(-s*0.28,-s*0.05,s*0.17,0,Math.PI*2); c.arc(s*0.28,-s*0.05,s*0.17,0,Math.PI*2); c.fill();
      if (sparkEyes){                       // jagged yellow spark pupils (electrical / metal)
        c.fillStyle='#fde047';
        for (var k=0;k<2;k++){ var ex=(k?1:-1)*s*0.28;
          c.beginPath();
          for (var a=0;a<8;a++){ var ang=a*Math.PI/4 + tt*3 + ph; var rad=(a%2? s*0.15 : s*0.06);
            var px=ex+Math.cos(ang)*rad, py=-s*0.05+Math.sin(ang)*rad; a?c.lineTo(px,py):c.moveTo(px,py); }
          c.closePath(); c.fill(); }
      } else {
        c.fillStyle='#101418';
        c.beginPath(); c.arc(-s*0.28,-s*0.02,s*0.07,0,Math.PI*2); c.arc(s*0.28,-s*0.02,s*0.07,0,Math.PI*2); c.fill();
      }
      c.strokeStyle='#101418'; c.lineWidth=Math.max(2,s*0.06); c.lineCap='round';
      c.beginPath(); c.moveTo(-s*0.45,-s*0.35); c.lineTo(-s*0.12,-s*0.2); c.moveTo(s*0.45,-s*0.35); c.lineTo(s*0.12,-s*0.2); c.stroke();
      c.beginPath(); c.moveTo(-s*0.2,s*0.34); c.quadraticCurveTo(0,s*0.5,s*0.2,s*0.34); c.stroke();
    }
    // The shared two-tone flame body. ITEM-052: the motion is turned up so fires read as
    // lively rather than nearly still — the flame licks side to side (anchored at its base
    // so it doesn't drift off the burning object), the whole flame breathes, and the hot
    // inner core flickers harder. All driven off the existing per-fire flicker value, so no
    // extra work per frame and each fire still moves on its own phase. Works at any size, so
    // it composes with the bigger flames (ITEM-051) and the resist-shrink (ITEM-041).
    function drawFlameBody(c, s, col, flick){
      var lean = flick*0.16;                       // side-to-side lick amount
      c.save();
      c.transform(1, 0, lean, 1, -lean*s, 0);      // shear anchored at the base (y=+s): the tip sways, the base stays put
      c.fillStyle=col; flameShape(c, s, 1 + flick*0.06); c.fill();                         // outer flame breathes
      c.save(); c.translate(0, s*0.18); c.fillStyle=shade(col,0.42); flameShape(c, s, 0.55 + flick*0.22); c.fill(); c.restore();  // inner core flickers harder
      c.restore();
    }
    // Draw the per-type character in the fire's local (translated) coordinates.
    function drawFireCharacter(c, cls, s, col, tt, ph, hc){
      var flick = Math.sin(tt*8 + ph);
      if (cls==='F'){                        // cooking oil — a burning pan
        drawFlameBody(c, s*0.9, col, flick);
        drawEvilFace(c, s*0.9, false, tt, ph);
        c.fillStyle = hc ? '#c3cee0' : '#2b3546';   // dark pan silhouette at the base
        c.beginPath(); c.ellipse(0, s*0.72, s*0.7, s*0.22, 0, 0, Math.PI); c.fill();
        rr(c, -s*0.72, s*0.6, s*1.44, s*0.16, s*0.06); c.fill();
        rr(c, s*0.66, s*0.58, s*0.72, s*0.12, s*0.05); c.fill();   // handle
      } else if (cls==='B'){                 // liquids — bubbling green pool with flames
        var green = hc ? '#5fd47a' : '#2ba84a';
        c.save();                            // green pool (two-tone ellipse)
        c.fillStyle=shade(green,-0.2); c.beginPath(); c.ellipse(0, s*0.72, s*0.85, s*0.3, 0,0,Math.PI*2); c.fill();
        c.fillStyle=green; c.beginPath(); c.ellipse(0, s*0.68, s*0.78, s*0.24, 0,0,Math.PI*2); c.fill();
        c.restore();
        drawFlameBody(c, s*0.92, col, flick);       // flames (class colour) on the liquid
        for (var bi=0; bi<3; bi++){                  // rising bubbles
          var bp=((tt*0.6 + bi*0.4 + ph)%1), by=s*0.72 - bp*s, bx=(bi-1)*s*0.32;
          c.globalAlpha=Math.max(0,1-bp); c.fillStyle=shade(green,0.5);
          c.beginPath(); c.arc(bx, by, s*0.1*(1-bp*0.4), 0, Math.PI*2); c.fill();
        }
        c.globalAlpha=1;
        drawEvilFace(c, s*0.92, false, tt, ph);
      } else if (cls==='electrical'){        // electrical — spark eyes + thrown mini-sparks
        drawFlameBody(c, s, col, flick);
        c.strokeStyle = hc ? '#fff27a' : '#fde047'; c.lineWidth=Math.max(1.5,s*0.05); c.lineCap='round';
        for (var si=0; si<4; si++){
          var sp=((tt*1.4 + si*0.25 + ph)%1), ang=ph + si*1.9 + tt*0.5, r0=s*0.6 + sp*s*0.9;
          var sx=Math.cos(ang)*r0, sy=Math.sin(ang)*r0 - s*0.1;
          c.globalAlpha=Math.max(0,1-sp);
          c.beginPath(); c.moveTo(sx,sy); c.lineTo(sx+Math.cos(ang)*s*0.22, sy+Math.sin(ang)*s*0.22); c.stroke();
        }
        c.globalAlpha=1;
        c.beginPath(); c.moveTo(-s*0.1,-s*0.5); c.lineTo(s*0.06,-s*0.2); c.lineTo(-s*0.05,-s*0.05); c.lineTo(s*0.1,s*0.25); c.stroke();
        drawEvilFace(c, s, true, tt, ph);
      } else if (cls==='D'){                 // metals — intense white-hot spark-burst
        var white = hc ? '#ffffff' : '#f8fafc';
        drawFlameBody(c, s, col, flick);
        c.fillStyle='rgba(255,255,255,'+(0.5+0.35*Math.abs(Math.sin(tt*7+ph)))+')';
        c.beginPath(); c.arc(0, s*0.05, s*0.32, 0, Math.PI*2); c.fill();
        var burst=0.5+0.5*Math.sin(tt*9+ph);
        c.strokeStyle=white; c.lineWidth=Math.max(1.5,s*0.055); c.lineCap='round';
        for (var di=0; di<8; di++){ var a2=di*Math.PI/4 + tt*0.8, r1=s*0.5, r2=s*(0.8+0.35*burst);
          c.globalAlpha=0.4+0.5*burst;
          c.beginPath(); c.moveTo(Math.cos(a2)*r1, Math.sin(a2)*r1 - s*0.05); c.lineTo(Math.cos(a2)*r2, Math.sin(a2)*r2 - s*0.05); c.stroke(); }
        c.globalAlpha=1;
        drawEvilFace(c, s, true, tt, ph);
      } else if (cls==='C'){                 // gases — a sharp hissing jet flame + valve
        var jw=Math.sin(tt*10+ph)*s*0.12;
        c.fillStyle=shade(col,-0.3); rr(c, -s*0.2, s*0.55, s*0.4, s*0.35, s*0.08); c.fill();   // valve
        c.save(); c.translate(0,-s*0.1);
        c.fillStyle=col;                     // sharp elongated jet with a waver
        c.beginPath(); c.moveTo(-s*0.35,s*0.5); c.quadraticCurveTo(-s*0.1+jw,-s*0.4, jw,-s*1.05); c.quadraticCurveTo(s*0.1+jw,-s*0.4, s*0.35,s*0.5); c.closePath(); c.fill();
        c.fillStyle=shade(col,0.4);
        c.beginPath(); c.moveTo(-s*0.16,s*0.4); c.quadraticCurveTo(jw,-s*0.2, jw*0.6,-s*0.7); c.quadraticCurveTo(s*0.16,-s*0.2, s*0.16,s*0.4); c.closePath(); c.fill();
        c.restore();
        drawEvilFace(c, s, false, tt, ph);
      } else {                               // solids (A) + fallback — classic flame + ember log
        drawFlameBody(c, s, col, flick);
        c.fillStyle = hc ? '#5b3a22' : '#7a4a25';   // glowing ember log at the base
        rr(c, -s*0.5, s*0.62, s*1.0, s*0.28, s*0.12); c.fill();
        var eg=0.5+0.5*Math.sin(tt*6+ph);
        c.fillStyle='rgba(255,170,60,'+(0.35+0.4*eg)+')';
        c.beginPath(); c.arc(-s*0.2, s*0.76, s*0.08, 0, Math.PI*2); c.arc(s*0.18, s*0.76, s*0.07, 0, Math.PI*2); c.fill();
        drawEvilFace(c, s, false, tt, ph);
      }
    }
    function drawFire(f){
      var p = pathPointAt(game.level.path, f.progress);
      var cls = classMap[f.cls] || {icon:'🔥', letter:'?'};
      var col = classColour(f.cls);
      var hc = contrastEnabled;
      var reacting = f.reaction && performance.now() < (f.reactionUntil||0);
      var s = 26, x = p[0], y = p[1];                 // s stays the layout unit for badge/icon/rings
      var fs = s * 1.9;                                // flame size — roughly double, CHARACTER only
      var baseY = y + s*0.55;                          // base anchor line on the path
      var tt = performance.now()*0.001;
      var ph = (f.id||0)*1.7;                          // per-fire phase (no lockstep)
      // ITEM-041 + ITEM-051 merged: the fire visibly RESISTS being worn down — the
      // flame character shrinks toward the kill as hp drops (greyscale/hc-safe: a
      // size cue, not a colour cue), plus a dashed amber "resisting" ring. Adam's
      // ITEM-051 bigger, base-anchored flame (fs) is the full-health size; it scales
      // down with remaining hp while the base stays anchored on the path.
      var hpFrac = (f.hp===undefined) ? 1 : Math.max(0, Math.min(1, f.hp));
      var flameScale = fs * (0.62 + 0.38*hpFrac);      // shrinks as the fire is worn down
      if (hpFrac < 0.999 && hpFrac > 0){
        ctx.setLineDash([3,3]); ctx.beginPath(); ctx.arc(x, baseY - fs*0.6, fs*0.9, 0, Math.PI*2);
        ctx.strokeStyle = hc ? '#fde68a' : '#d97706'; ctx.lineWidth=2; ctx.stroke(); ctx.setLineDash([]);
      }
      // reaction rings — KEEP the exact shapes (solid red = danger, dashed grey = useless), recentred on the taller flame
      if (reacting && f.reaction==='danger'){
        ctx.beginPath(); ctx.arc(x,baseY - fs*0.6,fs*1.05,0,Math.PI*2); ctx.strokeStyle='#b91c1c'; ctx.lineWidth=4; ctx.stroke();
      } else if (reacting && f.reaction==='useless'){
        ctx.setLineDash([4,4]); ctx.beginPath(); ctx.arc(x,baseY - fs*0.6,fs*1.0,0,Math.PI*2); ctx.strokeStyle='#9ca3af'; ctx.lineWidth=3; ctx.stroke(); ctx.setLineDash([]);
      }
      // the distinctive animated character (per type) — Adam's enlarged base-anchored
      // flame, scaled down by remaining hp (ITEM-041) so it shrinks as it goes out.
      ctx.save(); ctx.translate(x, baseY - flameScale*0.72);
      drawFireCharacter(ctx, f.cls, flameScale, col, tt, ph, hc);
      ctx.restore();
      // letter badge (white circle + dark letter) — survives greyscale, KEPT size (from s), moved clear of the tall flame
      ctx.fillStyle='#fff'; ctx.strokeStyle='rgba(0,0,0,.18)'; ctx.lineWidth=1;
      ctx.beginPath(); ctx.arc(x+fs*0.62,baseY - fs*1.15,s*0.42,0,Math.PI*2); ctx.fill(); ctx.stroke();
      ctx.fillStyle='#101418'; ctx.font='700 '+(s*0.62)+'px system-ui'; ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillText(cls.letter||'?', x+fs*0.62, baseY - fs*1.15);
      // class icon below the burning object — KEPT
      ctx.font=(s*0.7)+'px system-ui'; ctx.fillStyle='#101418'; ctx.fillText(cls.icon||'🔥', x, baseY + s*1.0);
      // danger warning glyph above the taller flame tip — KEPT
      if (reacting && f.reaction==='danger'){ ctx.font='15px system-ui'; ctx.fillText('⚠️', x, baseY - fs*1.72 - 12); }
      ctx.textBaseline='alphabetic';
    }
    function drawOverlay(){
      // Just a soft dim when the level is over; the detailed recap is an HTML modal.
      if (!game || game.status==='playing' || game.status==='idle') return;
      ctx.fillStyle = contrastEnabled ? 'rgba(11,13,18,.55)' : 'rgba(244,247,252,.55)';
      ctx.fillRect(0,0,canvas.width,canvas.height);
    }

    // --- Reward vignettes + finale (ITEM-028) ---------------------------------
    // A tiny, self-contained canvas animation engine. Everything is guarded: if a
    // scene ever throws, the loop stops and the game keeps working (optional-feature
    // rule). Pure canvas/JS, no libraries.
    function updateAntonMood(){
      var el=document.getElementById('antonMood'); if (!el) return;
      if (!antonArc || !antonArc.length){ el.textContent=''; return; }
      var i=Math.max(0, Math.min(antonArc.length-1, campaignProgress));
      el.textContent='👻 ' + antonArc[i];
    }
    function stopVignetteAnim(){ if (vigRAF){ try { cancelAnimationFrame(vigRAF); } catch(e){} vigRAF=null; } }
    function runSceneLoop(canvasId, sceneName){
      var cv=document.getElementById(canvasId); if (!cv) return;
      var c=null; try { c=cv.getContext('2d'); } catch(e){ return; }
      if (!c) return;
      var start=performance.now();
      stopVignetteAnim();
      function step(now){
        var t=(now-start)/1000;
        try {
          c.clearRect(0,0,cv.width,cv.height);
          drawScene(c, cv.width, cv.height, t, sceneName);
        } catch(e){ stopVignetteAnim(); return; }   // never crash the page
        vigRAF=requestAnimationFrame(step);
      }
      vigRAF=requestAnimationFrame(step);
    }
    // Gentle, fictional scenes — soft motion only, no real names/events.
    function drawScene(c, w, h, t, name){
      if (name==='lantern'){
        // a warm lantern glow drifting up a dark half-timbered lane
        c.fillStyle='#0b0704'; c.fillRect(0,0,w,h);
        c.fillStyle='#1c140c';
        c.fillRect(0,0,w*0.22,h); c.fillRect(w*0.78,0,w*0.22,h);
        c.strokeStyle='rgba(120,80,40,.5)'; c.lineWidth=3;
        for (var i=1;i<5;i++){ c.beginPath(); c.moveTo(0,h*i/5); c.lineTo(w*0.22,h*i/5 - 18); c.stroke();
          c.beginPath(); c.moveTo(w*0.78,h*i/5-18); c.lineTo(w,h*i/5); c.stroke(); }
        var gy=h-40 - (t*26)%(h+30);
        var gr=c.createRadialGradient(w/2,gy,2, w/2,gy,46);
        gr.addColorStop(0,'rgba(255,214,140,.95)'); gr.addColorStop(1,'rgba(255,180,80,0)');
        c.fillStyle=gr; c.beginPath(); c.arc(w/2,gy,46,0,Math.PI*2); c.fill();
        c.fillStyle='#ffcf87'; c.beginPath(); c.arc(w/2,gy,6,0,Math.PI*2); c.fill();
        // neighbours passing buckets (dots bobbing)
        for (var b=0;b<5;b++){ var bx=w*0.30+b*w*0.1; var by=h-24+Math.sin(t*2+b)*4;
          c.fillStyle='#e7c9a0'; c.beginPath(); c.arc(bx,by,5,0,Math.PI*2); c.fill(); }
      } else if (name==='records'){
        // parchment ledger, a highlight sweeps down and reveals a shimmering name
        c.fillStyle='#efe2c6'; c.fillRect(0,0,w,h);
        c.strokeStyle='rgba(90,70,40,.5)'; c.lineWidth=2;
        var lineY; for (var r=0;r<9;r++){ lineY=24+r*20; c.beginPath(); c.moveTo(30,lineY); c.lineTo(w-30, lineY); c.stroke(); }
        var nameY=24+4*20;
        var sweep=(t*40)%(h+40);
        c.fillStyle='rgba(255,240,180,.25)'; c.fillRect(0, sweep-16, w, 22);
        var glow=Math.max(0, Math.sin(t*1.5));
        c.globalAlpha=0.4+0.6*glow; c.strokeStyle='#b8860b'; c.lineWidth=3;
        c.beginPath(); c.moveTo(70, nameY); c.lineTo(w-120, nameY); c.stroke(); c.globalAlpha=1;
        c.fillStyle='rgba(184,134,11,'+(0.5+0.5*glow)+')'; c.font='italic 14px system-ui'; c.textAlign='left';
        c.fillText('… Anton, Wächter der Burg …', 74, nameY-5);
        drawGhost(c, w-70, h/2, 1.1, 0.7+0.25*glow, -0.05, false, glow>0.6);
      } else if (name==='storm'){
        // wind lines settle, stars come out, people gather safely below
        c.fillStyle='#0e1726'; c.fillRect(0,0,w,h);
        var calm=Math.min(1, t/3);
        c.strokeStyle='rgba(160,180,210,'+(0.5*(1-calm))+')'; c.lineWidth=2;
        for (var s=0;s<7;s++){ var yy=20+s*24+Math.sin(t*4+s)*6*(1-calm);
          c.beginPath(); c.moveTo(0,yy); c.lineTo(w*(0.5+0.5*(1-calm)), yy-10); c.stroke(); }
        for (var st=0; st<18; st++){ var sx=(st*53%w), sy=(st*29%(h*0.6));
          c.globalAlpha=calm*(0.4+0.6*Math.abs(Math.sin(t+st))); c.fillStyle='#fde68a';
          c.beginPath(); c.arc(sx,sy,1.5,0,Math.PI*2); c.fill(); }
        c.globalAlpha=1;
        c.fillStyle='#14532d'; c.beginPath(); c.arc(w*0.2,h-30,22,0,Math.PI*2); c.fill();
        c.fillStyle='#7a5230'; c.fillRect(w*0.2-4,h-26,8,20);
        for (var p=0;p<6;p++){ var px=w*0.45+p*24, py=h-22+Math.sin(t*1.5+p)*2;
          c.fillStyle='#cbd5e1'; c.beginPath(); c.arc(px,py,5,0,Math.PI*2); c.fill(); }
      } else if (name==='festival'){
        // night sky, gentle rising fireworks bursting, a warm crowd below
        c.fillStyle='#0a0614'; c.fillRect(0,0,w,h);
        for (var f=0; f<3; f++){
          var period=2.4, phase=(t + f*0.8)%period, cx=w*(0.25+0.25*f), topY=h*0.25+f*10;
          if (phase<1.0){ var ry=h-20-(h*0.7)*phase; c.fillStyle='#fca5a5';
            c.beginPath(); c.arc(cx,ry,2,0,Math.PI*2); c.fill(); }
          else { var br=(phase-1.0)*70, al=Math.max(0,1-(phase-1.0)/1.4);
            c.strokeStyle='rgba(253,224,120,'+al+')'; c.lineWidth=2;
            for (var a=0;a<10;a++){ var ang=a*Math.PI/5;
              c.beginPath(); c.moveTo(cx,topY); c.lineTo(cx+Math.cos(ang)*br, topY+Math.sin(ang)*br); c.stroke(); } }
        }
        for (var q=0;q<10;q++){ var qx=20+q*w*0.096, qy=h-16+Math.sin(t*2+q)*2;
          c.fillStyle='#e7c9a0'; c.beginPath(); c.arc(qx,qy,4,0,Math.PI*2); c.fill(); }
      } else if (name==='helmet'){
        // the community gathers and gives Anton the fire helmet, then he rises brighter
        c.fillStyle='#0a0614'; c.fillRect(0,0,w,h);
        var cx=w/2, cy=h*0.6;
        for (var d=0; d<14; d++){ var ang=d*(Math.PI*2/14), rr=Math.min(w,h)*0.42;
          var dx=cx+Math.cos(ang)*rr, dy=cy+Math.sin(ang)*rr*0.7 + Math.sin(t*1.4+d)*2;
          c.fillStyle='#c7b8e6'; c.beginPath(); c.arc(dx,dy,5,0,Math.PI*2); c.fill(); }
        var settle=Math.min(1, t/2.2);
        var bright=0.7+0.3*Math.min(1,Math.max(0,(t-2.2)/1.5));
        drawGhost(c, cx, cy, 1.6, 0.6+0.4*settle, (1-settle)*0.1, settle>=1, bright>0.9);
        if (settle<1){  // helmet descending onto his head
          var hy=cy-70 - (1-settle)* (h*0.35);
          c.save(); c.translate(cx, hy); c.rotate(-0.2); c.fillStyle='#dc2626';
          c.fillRect(-21,-3,42,8); c.beginPath(); c.arc(0,0,13,Math.PI,0); c.fill(); c.restore();
        }
        if (bright>0.9){ for (var k=0;k<8;k++){ var ka=t*2+k, kr=30+ (t*20)%40;
          c.globalAlpha=Math.max(0,1-((t*20)%40)/40); c.fillStyle='#fde68a';
          c.beginPath(); c.arc(cx+Math.cos(ka)*kr, cy-30+Math.sin(ka)*kr*0.6, 2,0,Math.PI*2); c.fill(); }
          c.globalAlpha=1; }
      }
    }
    function openVignette(vig, thenFinale){
      vignetteThenFinale = !!thenFinale;
      try {
        document.getElementById('vigTitle').textContent = (vig && vig.title) || '';
        document.getElementById('vigCaption').textContent = (vig && vig.caption) || '';
        document.getElementById('vignette').style.display='flex';
        runSceneLoop('vigCanvas', (vig && vig.scene) || 'lantern');
      } catch(e){
        stopVignetteAnim();
        var v=document.getElementById('vignette'); if (v) v.style.display='none';
        if (vignetteThenFinale){ vignetteThenFinale=false; openFinale(); } else showRecap();
      }
    }
    function closeVignette(){
      stopVignetteAnim();
      var v=document.getElementById('vignette'); if (v) v.style.display='none';
      if (vignetteThenFinale){ vignetteThenFinale=false; openFinale(); } else showRecap();
    }
    function openFinale(){
      var fin = antonFinale || {};
      try {
        document.getElementById('finTitle').textContent = fin.title || 'Finale';
        document.getElementById('finCaption').textContent = fin.caption || '';
        var box=document.getElementById('finLines'); box.innerHTML='';
        (fin.lines || []).forEach(function(ln){
          var p=document.createElement('p'); p.textContent=ln; p.style.margin='.4rem 0'; box.appendChild(p);
        });
        document.getElementById('finale').style.display='flex';
        runSceneLoop('finCanvas', fin.scene || 'helmet');
      } catch(e){
        stopVignetteAnim();
        var el=document.getElementById('finale'); if (el) el.style.display='none';
        showRecap();
      }
    }
    function closeFinale(){
      stopVignetteAnim();
      var el=document.getElementById('finale'); if (el) el.style.display='none';
      showRecap();
    }
    // Decide what plays when a level ends (ITEM-028): a campaign WIN unlocks its reward
    // vignette (then the finale if the whole campaign is now complete), then the recap.
    function handleEnd(){
      if (!game) return;
      var won = game.status==='won';
      var completedCampaign=false;
      if (won && isCampaign && missionNo){
        if (missionNo>campaignProgress){ campaignProgress=missionNo; saveProgress(); renderLevelBar(); updateAntonMood(); }
        completedCampaign = (campaignTotal()>0 && campaignProgress>=campaignTotal());
      }
      if (won && isCampaign && level && level.vignette && level.vignette.scene){
        openVignette(level.vignette, completedCampaign);
      } else if (won && completedCampaign){
        openFinale();
      } else {
        showRecap();
      }
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
        rows += '<div style="display:flex; align-items:center; gap:.5rem; padding:.25rem 0; border-top:1px solid var(--line);">' +
                '<span style="font-size:1.3rem;">'+(c.icon||'🔥')+'</span>' +
                '<span style="flex:1;">'+(c.name_de||ev['class'])+'</span>' +
                '<span style="color:var(--c);">Richtig: '+(rightActionFor(ev['class'])||'')+'</span></div>';
      });
      document.getElementById('recapClasses').innerHTML =
        '<div style="color:var(--muted); margin-bottom:.2rem;">Diese Feuer kamen vor:</div>' + rows;

      // Anton closes the mission and notes the rescue bonus. (Campaign progress is
      // already advanced in handleEnd(), before the reward vignette/finale plays.)
      var antonEl=document.getElementById('recapAnton');
      var nextBtn=document.getElementById('recapNext');
      antonEl.textContent=''; nextBtn.style.display='none';
      if (isCampaign && antonLines){
        var msg = '';
        if (game.status==='won'){
          msg = antonLines.close || '';
          if (game.leaked===0 && antonLines.bonus) msg += (msg ? '  ' : '') + '⭐ ' + antonLines.bonus;
        } else {
          // Never scold: a gentle, encouraging word on a loss.
          msg = 'Kein Grund zu hadern — beim nächsten Mal schaffen wir das zusammen.';
        }
        if (msg) antonEl.textContent = '👻 ' + msg;
        if (game.status==='won' && missionNo){
          var nxt=null;
          levelsMeta.forEach(function(l){ if (l.campaign && l.mission===missionNo+1) nxt=l; });
          if (nxt && missionUnlocked(nxt.mission)){
            nextBtn.style.display='';
            nextBtn.textContent='Nächster Einsatz ▶';
            nextBtn.onclick=function(){ document.getElementById('recap').style.display='none'; loadLevel(nxt.index); };
          }
        }
      }
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
        rows += '<div style="padding:.5rem 0; border-top:1px solid var(--line);">' +
          '<div style="font-weight:600;">'+(c.icon||'🔥')+' '+(c.name_de||cid)+'</div>' +
          '<div style="color:var(--ink);">'+(c.card_de||'')+'</div>' +
          '<div style="color:var(--c);">✓ Richtig: '+(goods.join(', ')||'—')+'</div>' +
          (dangers.length ? '<div style="color:var(--red);">⚠️ Gefährlich: '+dangers.join(', ')+'</div>' : '') +
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
        g.fires.push({id:g.nextId++, cls:scls, progress:0, hp:FIRE_HP}); g.spawned++;
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
          // supply still on: spraying does nothing — cut the supply first. ITEM-040:
          // a shot that plainly can't touch this fire never spends any charge.
          target.reaction='useless'; target.reactionUntil=performance.now()+500;
          showFeedback(HAZARD_WARN[thaz], 'danger');
          playSound('danger');
          g.useless++;
          continue;
        }
        var outcome = matrixMap[target.cls + '|' + tw.tool];
        if (outcome==='good' || outcome==='weak'){
          // ITEM-040: this shot actually discharged at the fire, so it costs a charge.
          // ITEM-041: it wears the fire's resistance down — "good" clears it in one
          // hit, "weak" needs another — and the reward + smart bonus are only paid
          // out on the actual put-out.
          tw.charge--;
          var dmg = (outcome==='good') ? GOOD_HIT_DAMAGE : WEAK_HIT_DAMAGE;
          target.hp = (target.hp===undefined ? FIRE_HP : target.hp) - dmg;
          if (target.hp <= 1e-9){
            g.fires = g.fires.filter(function(f){ return f.id!==target.id; });
            g.budget += EXTINGUISH_REWARD + (outcome==='good' ? SMART_BONUS : 0); updateBudget();
            g.ext++;
          } else {
            target.reaction='hit'; target.reactionUntil=performance.now()+400;
          }
          playSound('good');
        } else if (outcome==='danger'){
          // ITEM-040: a dangerous mismatch DID discharge the extinguisher (badly),
          // so it costs a charge too — the wrong choice is never cheaper.
          tw.charge--;
          target.progress = Math.min(0.999, target.progress + DANGER_SPEEDUP);
          target.reaction='danger'; target.reactionUntil=performance.now()+500;
          showFeedback(reasonMap[target.cls + '|' + tw.tool], 'danger');
          playSound('danger');
          g.danger++;
          // ITEM-034: water on a liquid/cooking-oil fire can split it in two.
          if (tw.tool==='water' && (target.cls==='B' || target.cls==='F') && g.fires.length < MAX_ACTIVE_FIRES){
            g.fires.push({id:g.nextId++, cls:target.cls, progress:Math.max(0, target.progress-0.05), hp:FIRE_HP});
          }
        } else {
          // Useless tool: nothing happens, the shot is wasted, no budget, and
          // (ITEM-040) no charge.
          target.reaction='useless'; target.reactionUntil=performance.now()+500;
          showFeedback(reasonMap[target.cls + '|' + tw.tool], 'useless');
          playSound('useless');
          g.useless++;
        }
      }
      // ITEM-040: a tower with no charge left is spent — remove it, freeing the spot.
      g.towers = g.towers.filter(function(tw){ return tw.charge > 0; });
      // move fires; arrivals cost a life
      var still=[];
      for (var i=0;i<g.fires.length;i++){
        var f=g.fires[i]; f.progress += g.speed*dt;
        if (f.progress>=1){ g.lives--; g.leaked++; g.flashUntil=performance.now()+350; } else still.push(f);
      }
      g.fires=still;
      if (g.lives<=0){ g.lives=0; g.status='lost'; if (!g.fledAt) g.fledAt=performance.now(); return; }
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
               towers:[], nextTowerId:0, status:'idle', flashUntil:0, fledAt:0,
               ext:0, danger:0, useless:0, leaked:0, supplies:sup };
    }
    function onStartButton(){
      initAudio();   // first real user gesture — unlock/resume audio (autoplay-safe)
      if (!game) return;
      if (game.status==='idle'){ game.status='playing'; last=performance.now(); }
      else if (game.status==='won' || game.status==='lost'){
        game=newGame(level); sprays=[]; hintShown=false; seen={}; prevStatus='idle';
      }
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
      var charge=towerChargeFor(level);
      game.towers.push({id:game.nextTowerId++, spot_index:spotIndex, spot:spots[spotIndex], tool:toolId,
                         cooldown:0, charge:charge, maxCharge:charge});   // ITEM-040
      updateBudget();
      return true;
    }
    // ITEM-042: switch off / remove a (possibly wrongly-placed) extinguisher, freeing
    // its spot. NO REFUND — spent money is gone, on purpose, so removal can never be
    // used to cheese a win by recycling budget. A distinct path from placeTower (see
    // boardPlaceAt / the keyboard handler) so the one-tap-one-tower placement
    // guarantee is never touched.
    function removeTower(spotIndex){
      if (!game) return false;
      var before=game.towers.length;
      game.towers = game.towers.filter(function(tw){ return tw.spot_index!==spotIndex; });
      var removed = game.towers.length < before;
      if (removed){ showFeedback('Löscher abgebaut — kein Rückerstattung.', 'ok'); updateBudget(); }
      return removed;
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
      Array.prototype.forEach.call(document.querySelectorAll('#toolPalette .toolbtn'), function(btn){
        var cost=parseInt(btn.getAttribute('data-cost'),10);
        btn.disabled = (b < cost);
        btn.classList.toggle('active', btn.getAttribute('data-tool')===selectedTool);
      });
    }

    // Two-tone flat extinguisher in the tool's colour, with its short label.
    function drawTower(tw){
      var t=toolMap[tw.tool]||{hex:'#334155', short:'?'};
      var x=tw.spot[0], y=tw.spot[1];
      ctx.beginPath(); ctx.arc(x,y,TOWER_RANGE,0,Math.PI*2); ctx.fillStyle='rgba(47,111,237,.05)'; ctx.fill();
      // ITEM-055: the placed extinguisher is drawn 50% bigger (26x36 -> 39x54).
      // Only the DRAWING grows — the build-spot position and the tap/keyboard hit
      // area (nearestSpot / HIT_RADIUS) are unchanged, so placement is unaffected.
      var w=39, h=54;
      drawExtShape(ctx, x-w/2, y-h/2+3, w, h, toolColour(t.hex));
      ctx.fillStyle='#101418'; ctx.font='700 12px system-ui'; ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillText((t.short||'').slice(0,6), x, y+h*0.27);
      ctx.textBaseline='alphabetic';
      // ITEM-054 (moves ITEM-040's gauge): a shrinking charge gauge standing
      // VERTICALLY to the RIGHT of the extinguisher — full at the top, draining
      // downward as it fires — instead of a horizontal bar underneath. The FILL
      // LENGTH is the cue (greyscale/hc-safe, not colour alone); it turns a second,
      // distinct shade once low so it also reads without colour vision.
      var maxC = tw.maxCharge || tw.charge || 1;
      var frac = Math.max(0, Math.min(1, tw.charge / maxC));
      var gw=6, gh=h*0.82, gx=x + w/2 + 4, gy=(y - h/2 + 3) + (h - gh)/2;
      ctx.strokeStyle = contrastEnabled ? '#e5e7eb' : '#1f2937'; ctx.lineWidth=1;
      ctx.strokeRect(gx, gy, gw, gh);
      var low = frac <= 0.34;
      ctx.fillStyle = low ? (contrastEnabled?'#fca5a5':'#b91c1c') : (contrastEnabled?'#bbf7d0':'#15803d');
      var fillH = Math.max(0,(gh-2)*frac);
      ctx.fillRect(gx+1, gy+1+((gh-2)-fillH), gw-2, fillH);
    }
    function drawSprays(){
      var now=performance.now(), keep=[];
      for (var i=0;i<sprays.length;i++){ var s=sprays[i]; if (s.until<now) continue; keep.push(s);
        ctx.strokeStyle='rgba(255,255,255,.85)'; ctx.lineWidth=3;
        ctx.beginPath(); ctx.moveTo(s.x1,s.y1); ctx.lineTo(s.x2,s.y2); ctx.stroke();
      }
      sprays=keep;
    }

    function setLives(n){ var el=document.getElementById('lives'); if (el) el.textContent=''; }   // ITEM-058: on-screen lives counter removed — the house condition is the life gauge
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

    // One shared, styled two-tone flat background (sky gradient + a couple of simple
    // flat props). Per-mission distinct locations are a later item (ITEM-035), not here.
    // --- ITEM-035: per-mission location background --------------------------------
    // One soft per-level sky/wash gradient (computed ONCE, cached per level+size) plus
    // a few LOW-CONTRAST flat silhouette props that evoke the place. In high-contrast
    // mode the background becomes a plain dark field so it never hurts readability.
    var BG_STOPS = {
      fachwerk:   ['#e8eef7','#f6efe2'],   // pale day sky over the old lane
      bibliothek: ['#efe3c8','#e7d6b6'],   // warm amber library interior
      kurpark:    ['#8ea0b4','#c6d2de'],   // grey storm sky
      feuerwerk:  ['#241d47','#3a2f5e'],   // festival night
      schlosserei:['#d7dde5','#c3ccd6']    // cool grey workshop
    };
    var _bgGrad=null, _bgKey='';
    function bgGradient(w,h,key){
      var k=(key||'')+'|'+w+'x'+h;
      if (k!==_bgKey){
        var g=ctx.createLinearGradient(0,0,0,h);
        var st=BG_STOPS[key]||['#e6effb','#f6f9fd'];
        g.addColorStop(0,st[0]); g.addColorStop(1,st[1]);
        _bgGrad=g; _bgKey=k;
      }
      return _bgGrad;
    }
    function bgFachwerk(w,h){                     // a row of half-timbered houses, top
      for (var i=0;i<4;i++){ var x=30+i*235, y=18, bw=150, bh=86;
        ctx.fillStyle='#e6d7c0'; rr(ctx,x,y,bw,bh,4); ctx.fill();
        ctx.fillStyle='#b06a4a'; ctx.beginPath(); ctx.moveTo(x-8,y); ctx.lineTo(x+bw/2,y-24); ctx.lineTo(x+bw+8,y); ctx.closePath(); ctx.fill();
        ctx.strokeStyle='#8a6b4a'; ctx.lineWidth=3;
        ctx.strokeRect(x+3,y+3,bw-6,bh-6);
        ctx.beginPath(); ctx.moveTo(x+3,y+3); ctx.lineTo(x+bw-3,y+bh-3); ctx.moveTo(x+bw-3,y+3); ctx.lineTo(x+3,y+bh-3); ctx.stroke(); }
    }
    function bgBibliothek(w,h){                   // a bookshelf band + a stone arch, top
      ctx.fillStyle='#9a7b58'; rr(ctx,20,14,w-40,84,6); ctx.fill();
      var cols=['#b0563a','#3f6ea8','#6b8a4a','#9a6a3a','#7c5aa0'];
      for (var b=0;b*20<w-56;b++){ ctx.fillStyle=cols[b%5]; ctx.fillRect(30+b*20,22,15,68); }
      ctx.fillStyle='#7a6142'; ctx.fillRect(20,90,w-40,10);
      ctx.strokeStyle='#b79b74'; ctx.lineWidth=6; ctx.beginPath(); ctx.arc(w/2,116,140,Math.PI,0); ctx.stroke();
    }
    function bgKurpark(w,h){                      // storm clouds + trees + faint rain
      ctx.fillStyle='#8493a5';
      for (var i=0;i<4;i++){ var cx=90+i*250; ctx.beginPath(); ctx.arc(cx,46,40,0,Math.PI*2); ctx.arc(cx+42,58,30,0,Math.PI*2); ctx.arc(cx-40,58,26,0,Math.PI*2); ctx.fill(); }
      [w*0.14, w*0.86].forEach(function(tx){ var ty=150;
        ctx.fillStyle='#8a6238'; rr(ctx,tx-6,ty,12,34,3); ctx.fill();
        ctx.fillStyle='#6f9a5a'; ctx.beginPath(); ctx.arc(tx,ty-8,30,0,Math.PI*2); ctx.fill(); });
      ctx.strokeStyle='rgba(150,175,200,.5)'; ctx.lineWidth=1.5;
      for (var r=0;r<26;r++){ var rx=(r*47)%w, ry=(r*83)%(h*0.55); ctx.beginPath(); ctx.moveTo(rx,ry); ctx.lineTo(rx-6,ry+14); ctx.stroke(); }
    }
    function bgFeuerwerk(w,h){                    // night sky: stars, bunting, soft beams
      ctx.fillStyle='rgba(255,255,255,.75)';
      for (var s=0;s<28;s++){ ctx.fillRect((s*71)%w, (s*53)%(h*0.5), 2, 2); }
      var cols=['#e4572e','#f59e0b','#2f6fed','#14b8a6','#d6409f'];
      ctx.strokeStyle='#cfd6e0'; ctx.lineWidth=2; ctx.beginPath(); ctx.moveTo(0,26); ctx.lineTo(w,26); ctx.stroke();
      for (var i=0;i*44<w;i++){ var bx=i*44+12; ctx.fillStyle=cols[i%5];
        ctx.beginPath(); ctx.moveTo(bx-10,27); ctx.lineTo(bx+10,27); ctx.lineTo(bx,45); ctx.closePath(); ctx.fill(); }
      ctx.fillStyle='rgba(255,240,180,.10)';
      ctx.beginPath(); ctx.moveTo(w*0.3,0); ctx.lineTo(w*0.16,h); ctx.lineTo(w*0.42,h); ctx.closePath(); ctx.fill();
      ctx.beginPath(); ctx.moveTo(w*0.7,0); ctx.lineTo(w*0.58,h); ctx.lineTo(w*0.85,h); ctx.closePath(); ctx.fill();
    }
    function bgSchlosserei(w,h){                  // workshop: a window, a tool rack, a bench
      ctx.fillStyle='#c3ccd6'; rr(ctx,40,22,120,80,6); ctx.fill();
      ctx.strokeStyle='#8a97a6'; ctx.lineWidth=4; ctx.strokeRect(40,22,120,80);
      ctx.beginPath(); ctx.moveTo(100,22); ctx.lineTo(100,102); ctx.moveTo(40,62); ctx.lineTo(160,62); ctx.stroke();
      ctx.strokeStyle='#7a8494'; ctx.lineWidth=3; ctx.beginPath(); ctx.moveTo(w-230,40); ctx.lineTo(w-40,40); ctx.stroke();
      ctx.fillStyle='#8a97a6';
      ctx.fillRect(w-206,42,6,32); ctx.fillRect(w-212,72,18,8);            // hammer
      ctx.fillRect(w-150,42,4,38);                                          // driver
      ctx.lineWidth=4; ctx.strokeStyle='#8a97a6'; ctx.beginPath(); ctx.arc(w-100,58,13,0,Math.PI*1.4); ctx.stroke();  // wrench loop
      ctx.fillStyle='#9aa4b0'; ctx.fillRect(0,h-24,w,24);                   // workbench along the bottom
    }
    function drawBackground(){
      var w=canvas.width, h=canvas.height, key=level&&level.key;
      if (contrastEnabled){ ctx.fillStyle='#0b0d12'; ctx.fillRect(0,0,w,h); return; }  // plain dark field
      ctx.fillStyle=bgGradient(w,h,key); ctx.fillRect(0,0,w,h);
      ctx.save(); ctx.globalAlpha=0.5;                                       // low-contrast, decorative
      if (key==='fachwerk')       bgFachwerk(w,h);
      else if (key==='bibliothek')bgBibliothek(w,h);
      else if (key==='kurpark')   bgKurpark(w,h);
      else if (key==='feuerwerk') bgFeuerwerk(w,h);
      else if (key==='schlosserei')bgSchlosserei(w,h);
      ctx.restore();
    }
    // Draw Anton the ghost at (x,y) on any context. Shared by the board, the reward
    // vignettes and the finale so his look stays consistent. (ITEM-028)
    //   alpha = how solid he is, tilt = posture, helmet = wears the fire helmet,
    //   bright = a touch brighter + a small smile (braver).
    function drawGhost(c, x, y, scale, alpha, tilt, helmet, bright){
      c.save();
      c.translate(x, y); c.rotate(tilt||0); c.scale(scale, scale);
      var body = cssv('--blue') || '#2f6fed';
      c.globalAlpha = Math.max(0.2, Math.min(1, alpha));
      // TONE 1 — body (a touch brighter when braver)
      c.fillStyle = bright ? shade(body,0.12) : body;
      c.beginPath(); c.arc(0,0,18,Math.PI,0);
      c.lineTo(18,16);
      c.quadraticCurveTo(9,24, 0,16);
      c.quadraticCurveTo(-9,24, -18,16);
      c.closePath(); c.fill();
      // TONE 2 — lighter belly
      c.fillStyle = shade(body, 0.45);
      c.beginPath(); c.arc(0,2,11,Math.PI*0.15,Math.PI*0.85); c.fill();
      c.globalAlpha = Math.min(1, alpha+0.12);
      c.fillStyle='#fff';
      c.beginPath(); c.arc(-6,-2,4,0,Math.PI*2); c.arc(6,-2,4,0,Math.PI*2); c.fill();
      c.fillStyle='#101418';
      c.beginPath(); c.arc(-6,-1,2,0,Math.PI*2); c.arc(6,-1,2,0,Math.PI*2); c.fill();
      if (bright){  // a small confident smile
        c.strokeStyle='#101418'; c.lineWidth=1.5; c.beginPath(); c.arc(0,4,5,0.15*Math.PI,0.85*Math.PI); c.stroke();
      }
      if (helmet){  // the little crooked fire helmet — only from the finale onward
        c.save(); c.translate(0,-15); c.rotate(-0.2); c.globalAlpha=1; c.fillStyle=cssv('--red')||'#dc2626';
        c.fillRect(-13,-2,26,5); c.beginPath(); c.arc(0,0,8,Math.PI,0); c.fill(); c.restore();
      }
      c.restore();
    }
    function campaignTotal(){
      var n=0; levelsMeta.forEach(function(l){ if (l.campaign && l.mission) n++; }); return n;
    }
    // Anton grows braver with each completed mission (0..1).
    function antonBraveryFactor(){
      var tot = campaignTotal() || 4;
      return Math.max(0, Math.min(1, campaignProgress / tot));
    }
    // He only wears the helmet once the WHOLE campaign is complete (the finale gift).
    function antonWearsHelmet(){
      var tot = campaignTotal() || 4;
      return campaignProgress >= tot;
    }
    // ITEM-033: how worried Anton looks THIS level, driven by remaining lives (0 =
    // calm .. 1 = about to lose). Deliberately SEPARATE from antonBraveryFactor
    // (which tracks campaign/win progress across missions, not this level's
    // danger) — his win-side brave arc/helmet/finale are completely unaffected.
    function antonWorryFactor(){
      if (!game || !game.level || !game.level.building) return 0;
      var start = game.level.building.lives || 1;
      return 1 - Math.max(0, Math.min(1, game.lives / start));
    }
    function drawAnton(){
      var now=performance.now();
      var f=antonBraveryFactor();
      var worry=antonWorryFactor();
      // braver = rises up, stands more upright, more solid, a touch brighter.
      var x=canvas.width-44;
      var y=(54 - 14*f) + Math.sin(now/500)*(6 - 2*f);
      var alpha=0.5 + 0.45*f;
      var tilt=(1-f)*0.18 + Math.sin(now/900)*0.02;
      // ITEM-033: once the building has fallen (lives===0), Anton flees off-screen —
      // presentation only, the lose condition (lives<=0 in advance()) is unchanged.
      if (game && game.lives<=0 && game.fledAt){
        var since=(now-game.fledAt)/1000;
        y -= since*70; x += since*40;
        alpha = Math.max(0, alpha - since*0.5);
        tilt = -0.6 - since*0.3;
        if (alpha<=0) return;                 // fully flown off — nothing left to draw
        drawGhost(ctx, x, y, 1, alpha, tilt, antonWearsHelmet(), false);
        return;
      }
      // Worried: a lower, twitchier stance and a touch fainter the fewer lives
      // remain — additive with (not a replacement for) the bravery stance above.
      y += worry*10; tilt += worry*0.14 * Math.sin(now/220); alpha -= worry*0.15;
      drawGhost(ctx, x, y, 1, Math.max(0.15,alpha), tilt, antonWearsHelmet(), f>0.6);
    }
    // Anton "senses" the trouble and marks the spot where fire will break out
    // (ITEM-026): a gentle pulsing ring at the start of the path with a small note,
    // shown before the operation begins. Simple shapes in the game's own art style.
    function drawSense(wp){
      if (!wp || !wp.length) return;
      var now=performance.now();
      var x=wp[0][0], y=wp[0][1];
      var r=24 + Math.sin(now/300)*6;
      ctx.save();
      ctx.strokeStyle='rgba(180,83,9,.55)'; ctx.lineWidth=2;
      ctx.beginPath(); ctx.arc(x,y,r,0,Math.PI*2); ctx.stroke();
      ctx.beginPath(); ctx.arc(x,y,r*0.55,0,Math.PI*2); ctx.stroke();
      ctx.fillStyle='#b45309'; ctx.font='12px system-ui'; ctx.textAlign='left';
      ctx.fillText('👻 Anton wittert hier Rauch', x+r+4, y-2);
      ctx.restore();
    }

    function render(){
      if (!level) return;
      ctx.clearRect(0,0,canvas.width,canvas.height);
      drawBackground();
      drawPath(level.path);
      level.build_spots.forEach(function(s, idx){ var tw=towerAt(idx); if (tw) drawTower(tw); else drawBuildSpot(s[0],s[1]); });
      drawKeyHighlight();
      drawStart(level.path);
      // Before the operation starts, Anton marks where fire will break out.
      if (!game || game.status==='idle') drawSense(level.path);
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
      el.style.color = (kind==='danger') ? 'var(--red)' : 'var(--muted)';
      feedbackUntil = performance.now() + 2600;
    }
    function showCard(cls){
      var c=classMap[cls]||{}; paused=true;
      document.getElementById('cardIcon').textContent = c.icon || '🔥';
      document.getElementById('cardTitle').textContent = (c.name_de||'') + (c.letter ? (' ('+c.letter+')') : '');
      document.getElementById('cardText').textContent = c.card_de || '';
      document.getElementById('card').style.display = 'flex';
    }
    // Anton opens a story mission (ITEM-026/027): he senses the trouble and tells a
    // short Königstein anecdote. One calm card at the start — reuses the existing
    // card modal + toggle, so it can be turned off and doesn't stack extra pauses.
    function showMissionIntro(){
      if (!cardsEnabled || !isCampaign || !antonLines || !antonLines.open) return;
      document.getElementById('cardIcon').textContent = '👻';
      document.getElementById('cardTitle').textContent =
        (missionNo ? ('Einsatz ' + missionNo + ' · ') : '') + (level ? level.name : '');
      var el=document.getElementById('cardText'); el.textContent='';
      var parts=[antonLines.open];
      if (antonLines.anecdote) parts.push(antonLines.anecdote);
      parts.forEach(function(p, idx){
        if (idx>0){ el.appendChild(document.createElement('br')); el.appendChild(document.createElement('br')); }
        el.appendChild(document.createTextNode(p));
      });
      document.getElementById('card').style.display='flex';
      paused=true;
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
      if (game && game.status==='playing' && !paused){
        advance(dt); maybeShowCard();
        // Anton whispers ONE light, safe tactical hint a moment into the operation.
        if (!hintShown && antonLines && antonLines.hint && game.elapsed > 2.5){
          showFeedback(antonLines.hint, 'ok');
          feedbackUntil = performance.now() + 6500;  // give the hint a little longer
          hintShown = true;
        }
      }
      if (performance.now() > feedbackUntil) document.getElementById('feedback').textContent='';
      render();
      if (game && game.status!==prevStatus){
        if (game.status==='won'){ playSound('win'); handleEnd(); }
        else if (game.status==='lost'){ playSound('lose'); handleEnd(); }
        updateControls();
        prevStatus = game.status;
      }
      requestAnimationFrame(frame);
    }

    function loadLevel(i){
      fetch('/api/level/'+i).then(function(r){return r.json();}).then(function(data){
        if (data.error) return;
        level = data; game = newGame(level); sprays = []; prevStatus='idle';
        seen = {}; paused = false; hintShown = false; currentIndex = i; keyIndex = -1;
        antonLines = data.anton || {};
        missionKey = data.key; missionNo = data.mission; isCampaign = !!data.campaign;
        document.getElementById('card').style.display = 'none';
        document.getElementById('recap').style.display = 'none';
        document.getElementById('feedback').textContent = '';
        canvas.width = data.size.w; canvas.height = data.size.h;
        document.getElementById('place').textContent = data.name + ' · ' + data.place_de;
        setLives(data.building.lives);
        updateControls(); updateBudget(); renderLevelBar(); updateAntonMood();
        // Anton opens the mission by sensing it and telling his anecdote.
        showMissionIntro();
      }).catch(function(){ document.getElementById('place').textContent='Einsatz konnte nicht geladen werden.'; });
    }

    // ITEM-036: each tool is a card with a two-tone flat extinguisher graphic + label
    // (name/slot + cost) + an "ℹ Info" affordance. Clicking the card selects the tool
    // for placement (the game action); ℹ opens the info pop-up. Tools stay tellable
    // apart by label + shape (not colour), keyboard-selectable (1..N) and touch-sized.
    function loadTools(){
      return fetch('/api/tools').then(function(r){return r.json();}).then(function(list){
        toolsList=list; var bar=document.getElementById('toolPalette'); bar.innerHTML='';
        list.forEach(function(t, idx){
          toolMap[t.id]=t;
          var wrap=document.createElement('div'); wrap.className='tool';
          var btn=document.createElement('button'); btn.className='toolbtn';
          btn.setAttribute('data-tool', t.id); btn.setAttribute('data-cost', t.cost);
          btn.setAttribute('aria-label', t.name_de + ' — ' + t.cost);
          var cv=document.createElement('canvas'); cv.className='toolcv'; cv.width=34; cv.height=46; cv.setAttribute('data-tool', t.id);
          var nm=document.createElement('span'); nm.className='tname'; nm.textContent=(idx+1)+'. '+t.short;
          var cs=document.createElement('span'); cs.className='tcost'; cs.textContent='💰 '+t.cost;
          btn.appendChild(cv); btn.appendChild(nm); btn.appendChild(cs);
          btn.onclick=function(){ selectedTool=t.id; updateBudget(); };
          var info=document.createElement('button'); info.className='toolinfo'; info.textContent='ℹ Info';
          info.setAttribute('aria-label', 'Info: ' + t.name_de);
          info.onclick=function(){ openToolInfo(t.id); };
          wrap.appendChild(btn); wrap.appendChild(info); bar.appendChild(wrap);
        });
        paintToolCanvases();
      }).catch(function(){});
    }
    // Draw the little extinguisher graphic on each palette card (also redrawn when the
    // high-contrast theme changes, so the tool colour stays readable).
    function paintToolCanvases(){
      Array.prototype.forEach.call(document.querySelectorAll('#toolPalette canvas.toolcv'), function(cv){
        var t=toolMap[cv.getAttribute('data-tool')]; if (!t) return;
        var c=null; try { c=cv.getContext('2d'); } catch(e){ return; }
        if (!c) return;
        c.clearRect(0,0,cv.width,cv.height);
        drawExtShape(c, 8, 12, 18, 26, toolColour(t.hex));
      });
    }
    // Tool info pop-up (ITEM-036). Facts are DERIVED from the guarded fire-safety
    // matrix (same source as "Antons Wissen") — nothing is invented here.
    function openToolInfo(id){
      var t=toolMap[id]; if (!t) return;
      selectedTool=id; updateBudget();                 // selecting still selects for placement
      document.getElementById('tiTitle').textContent = t.name_de + ' (' + t.short + ')';
      var cv=document.getElementById('tiCanvas'), c=null;
      try { c=cv.getContext('2d'); } catch(e){ c=null; }
      if (c){ c.clearRect(0,0,cv.width,cv.height); drawExtShape(c, 18, 20, 26, 40, toolColour(t.hex)); }
      var goods=[], weaks=[], dangers=[];
      (window._classOrder||[]).forEach(function(cid){
        var o=matrixMap[cid+'|'+id], cc=classMap[cid]||{};
        var lab=(cc.icon||'')+' '+(cc.name_de||cid)+' ('+(cc.letter||'')+')';
        if (o==='good') goods.push(lab); else if (o==='danger') dangers.push(lab); else if (o==='weak') weaks.push(lab);
      });
      var html='<p style="color:var(--muted); margin:.2rem 0;">Kosten zum Aufstellen: 💰 '+t.cost+'</p>';
      html+='<div style="color:var(--c); margin:.2rem 0;">✓ Richtig gegen: '+(goods.join(', ')||'—')+'</div>';
      if (weaks.length) html+='<div style="color:var(--muted); margin:.2rem 0;">≈ Notfalls brauchbar: '+weaks.join(', ')+'</div>';
      if (dangers.length) html+='<div style="color:var(--red); margin:.2rem 0;">⚠️ Gefährlich auf: '+dangers.join(', ')+'</div>';
      document.getElementById('tiBody').innerHTML=html;
      if (game && game.status==='playing') paused=true;
      document.getElementById('toolInfo').style.display='flex';
    }
    function closeToolInfo(){ document.getElementById('toolInfo').style.display='none'; paused=false; last=performance.now(); }

    // Tap/click a build spot to place the selected tool there. The screen point is
    // scaled to board coordinates (works when the board is shrunk on a tablet). The
    // hit radius is finger-friendly (ITEM-020).
    function nearestSpot(clientX, clientY){
      if (!level) return -1;
      var rect=canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return -1;
      var x=(clientX-rect.left)*(canvas.width/rect.width);
      var y=(clientY-rect.top)*(canvas.height/rect.height);
      var spots=level.build_spots, bestI=-1, bestD=null;
      for (var i=0;i<spots.length;i++){
        var d=Math.hypot(spots[i][0]-x, spots[i][1]-y);
        if (d<=HIT_RADIUS && (bestD===null || d<bestD)){ bestD=d; bestI=i; }
      }
      return bestI;
    }
    function boardPlaceAt(clientX, clientY){
      if (!game || !selectedTool || !level) return;
      var i=nearestSpot(clientX, clientY);
      if (i>=0){ keyIndex=i; placeTower(i, selectedTool); }
    }
    // ITEM-042: tapping/clicking an already-occupied spot while NO tool is selected
    // removes the tower there. A distinct path from placement — boardPlaceAt (and
    // placeTower) above are untouched, so whenever a tool IS selected a tap can only
    // ever place, never remove; the one-tap-one-tower placement guarantee holds.
    function boardTapAt(clientX, clientY){
      if (!game || !level) return;
      if (selectedTool){ boardPlaceAt(clientX, clientY); return; }
      var i=nearestSpot(clientX, clientY);
      if (i>=0 && towerAt(i)){ keyIndex=i; removeTower(i); }
    }
    // ONE input path so a single tap can never place twice (touch + synthetic-click
    // double-fire is avoided): use Pointer Events where supported (covers mouse, touch
    // and pen); otherwise fall back to click + touchend, with touchend suppressing the
    // synthetic click. Desktop mouse behaves exactly as before.
    if (window.PointerEvent){
      canvas.addEventListener('pointerup', function(e){
        if (e.pointerType==='mouse' && e.button!==0) return;   // left mouse only
        boardTapAt(e.clientX, e.clientY);
      });
    } else {
      canvas.addEventListener('click', function(e){ boardTapAt(e.clientX, e.clientY); });
      canvas.addEventListener('touchend', function(e){
        if (e.changedTouches && e.changedTouches.length){
          e.preventDefault();                                  // stop the following synthetic click
          var t=e.changedTouches[0]; boardTapAt(t.clientX, t.clientY);
        }
      }, {passive:false});
    }

    // The level bar shows the four story missions in play order (locked until the
    // one before is won) plus the training level as a free-choice side level (ITEM-027).
    function renderLevelBar(){
      var bar=document.getElementById('levelBar'); if (!bar) return; bar.innerHTML='';
      var camp=levelsMeta.filter(function(l){ return l.campaign && l.mission; })
                         .slice().sort(function(a,b){ return a.mission-b.mission; });
      var side=levelsMeta.filter(function(l){ return !(l.campaign && l.mission); });
      camp.forEach(function(l){
        var unlocked=missionUnlocked(l.mission);
        var btn=document.createElement('button');
        btn.textContent='M'+l.mission+'. '+l.name + (unlocked ? '' : ' 🔒');
        btn.disabled=!unlocked;
        if (!unlocked) btn.title='Zuerst den vorherigen Einsatz gewinnen.';
        if (l.index===currentIndex) btn.className='active';
        btn.onclick=function(){ if (missionUnlocked(l.mission)) loadLevel(l.index); };
        bar.appendChild(btn);
      });
      side.forEach(function(l){
        var btn=document.createElement('button');
        btn.textContent='Übung: '+l.name;
        if (l.index===currentIndex) btn.className='active';
        btn.onclick=function(){ loadLevel(l.index); };
        bar.appendChild(btn);
      });
      // A small, unobtrusive "start over" control (clears saved campaign progress).
      var reset=document.createElement('button');
      reset.textContent='↺ Neu beginnen';
      reset.title='Kampagnen-Fortschritt löschen und wieder bei Einsatz 1 beginnen';
      reset.style.fontSize='.78rem'; reset.style.opacity='.65';
      reset.style.borderStyle='dashed'; reset.style.padding='.25rem .6rem';
      reset.onclick=resetProgress;
      bar.appendChild(reset);
    }
    function buildLevelBar(){
      fetch('/api/levels').then(function(r){return r.json();}).then(function(list){
        levelsMeta=list; loadProgress(); renderLevelBar();
        var camp=levelsMeta.filter(function(l){ return l.campaign && l.mission; })
                           .slice().sort(function(a,b){ return a.mission-b.mission; });
        loadLevel(camp.length ? camp[0].index : 0);
      });
    }

    function loadClasses(){
      return fetch('/api/classes').then(function(r){return r.json();}).then(function(list){
        var leg=document.getElementById('classLegend'); leg.innerHTML='';
        window._classOrder = list.map(function(c){ return c.id; });
        var CV={A:'--a',B:'--b',C:'--c',electrical:'--e',D:'--d',F:'--f'};
        list.forEach(function(c){
          classMap[c.id]=c;
          // Use the flat-palette CSS variable so the legend matches the canvas and
          // follows the high-contrast toggle automatically (visual only).
          var el=document.createElement('span'); el.style.color='var('+(CV[c.id]||'--ink')+')';
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
    // Anton's growth-arc lines + finale (ITEM-028). A fetch failure degrades quietly.
    function loadAnton(){
      return fetch('/api/anton').then(function(r){return r.json();}).then(function(d){
        antonArc = (d && d.courage) || []; antonFinale = (d && d.finale) || {};
        updateAntonMood();
      }).catch(function(){ antonArc=[]; antonFinale={}; });
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
    document.getElementById('vigClose').onclick = closeVignette;
    document.getElementById('finClose').onclick = closeFinale;
    document.getElementById('tiClose').onclick = closeToolInfo;

    // --- Große Schrift / Hoher Kontrast (ITEM-020) — presentational only, persisted
    //     with the same guarded localStorage pattern (a storage failure never throws).
    function applyContrast(on){
      contrastEnabled=!!on;
      if (document.body){ if (on) document.body.classList.add('hc'); else document.body.classList.remove('hc'); }
      var cb=document.getElementById('contrastToggle'); if (cb) cb.checked=!!on;
      paintToolCanvases();   // tool colours are lightened for the dark field — repaint
    }
    function saveContrast(on){ try { window.localStorage.setItem('fd_contrast', on?'1':'0'); } catch(e){} }
    function loadContrast(){ var on=false; try { on = window.localStorage.getItem('fd_contrast')==='1'; } catch(e){ on=false; } applyContrast(on); }
    document.getElementById('contrastToggle').onchange = function(e){ applyContrast(e.target.checked); saveContrast(e.target.checked); };
    loadContrast();

    // --- Ton / mute toggle (ITEM-019) — same wiring/persistence shape as the toggles
    //     above. Muted => playSound returns immediately, so nothing is heard.
    var _soundCb = document.getElementById('soundToggle');
    if (_soundCb) _soundCb.onchange = function(e){ soundEnabled = e.target.checked; saveSound(e.target.checked); if (soundEnabled) initAudio(); };
    loadSound();

    // --- ITEM-053 landscape-phone menus (Option B) — purely presentational: these
    //     handlers only toggle a "dd-open" class, which has no visual effect unless
    //     the landscape media query above is active, so they are harmless on desktop
    //     and portrait. Every element lookup is guarded, so a missing element (e.g.
    //     an older cached page) can never throw.
    (function(){
      var missionBtn = document.getElementById('missionMenuBtn');
      var gearBtn = document.getElementById('gearMenuBtn');
      var mLevelBar = document.getElementById('levelBar');
      var mSettings = document.getElementById('settingsGroup');
      function setOpen(el, btn, on){
        if (!el) return;
        el.classList.toggle('dd-open', !!on);
        if (btn) btn.setAttribute('aria-expanded', on ? 'true' : 'false');
      }
      function closeMenus(){ setOpen(mLevelBar, missionBtn, false); setOpen(mSettings, gearBtn, false); }
      if (missionBtn){
        missionBtn.onclick = function(e){
          if (e) e.stopPropagation();
          var willOpen = !(mLevelBar && mLevelBar.classList.contains('dd-open'));
          closeMenus(); setOpen(mLevelBar, missionBtn, willOpen);
        };
      }
      if (gearBtn){
        gearBtn.onclick = function(e){
          if (e) e.stopPropagation();
          var willOpen = !(mSettings && mSettings.classList.contains('dd-open'));
          closeMenus(); setOpen(mSettings, gearBtn, willOpen);
        };
      }
      if (mLevelBar){
        mLevelBar.addEventListener('click', function(e){
          if (e) e.stopPropagation();
          if (e && e.target && e.target.tagName === 'BUTTON') setOpen(mLevelBar, missionBtn, false);
        });
      }
      if (mSettings){
        mSettings.addEventListener('click', function(e){ if (e) e.stopPropagation(); });
      }
      document.addEventListener('click', closeMenus);
    })();

    // --- Spot-based keyboard control (ITEM-020): fully playable without a mouse.
    //     1..N pick an extinguisher; arrows move the build-spot highlight; Enter places;
    //     Space starts/restarts. Never hijacks a focused form control or button, and is
    //     inert while a modal/overlay is open, so it can't interfere with mouse/touch.
    function isFormFocus(){
      var el=document.activeElement; if (!el) return false;
      var tag=(el.tagName||'').toUpperCase();
      return tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT'||el.isContentEditable;
    }
    function isButtonFocus(){ var el=document.activeElement; return !!(el && (el.tagName||'').toUpperCase()==='BUTTON'); }
    function anyOverlayOpen(){
      var ids=['card','recap','lib','vignette','finale','toolInfo'];
      for (var i=0;i<ids.length;i++){ var el=document.getElementById(ids[i]);
        if (el && el.style.display && el.style.display!=='none') return true; }
      return false;
    }
    function moveHighlight(delta){
      if (!level || !level.build_spots.length) return;
      keyboardActive=true;
      if (keyIndex<0){ keyIndex=(delta>0?0:level.build_spots.length-1); }
      else { keyIndex=(keyIndex+delta+level.build_spots.length)%level.build_spots.length; }
    }
    function selectToolSlot(n){ if (!toolsList || n<1 || n>toolsList.length) return; selectedTool=toolsList[n-1].id; updateBudget(); }
    document.addEventListener('keydown', function(e){
      if (anyOverlayOpen() || isFormFocus()) return;
      var k=e.key;
      if (k>='1' && k<='9'){ selectToolSlot(parseInt(k,10)); e.preventDefault(); return; }
      if (k==='ArrowRight'||k==='ArrowDown'){ moveHighlight(1); e.preventDefault(); return; }
      if (k==='ArrowLeft'||k==='ArrowUp'){ moveHighlight(-1); e.preventDefault(); return; }
      if (k==='Enter'){
        if (isButtonFocus()) return;               // let a focused button activate normally
        keyboardActive=true;
        if (game && selectedTool && keyIndex>=0) placeTower(keyIndex, selectedTool);
        e.preventDefault(); return;
      }
      // ITEM-042/ITEM-020: Delete/Backspace removes the tower at the keyboard-
      // highlighted build spot — the keyboard-parity path for the same removal
      // boardTapAt offers by touch/click.
      if (k==='Delete'||k==='Backspace'){
        if (isButtonFocus()) return;
        if (game && keyIndex>=0) removeTower(keyIndex);
        e.preventDefault(); return;
      }
      if (k===' '||k==='Spacebar'){
        if (isButtonFocus()) return;               // let a focused button activate normally
        onStartButton(); e.preventDefault(); return;
      }
    });
    // Load classes, tools, the fire-safety matrix, and Anton's arc first, then levels.
    Promise.all([loadClasses(), loadTools(), loadMatrix(), loadAnton()]).then(function(){ buildLevelBar(); });
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
