"""The fire facts and every line Anton speaks — the teaching content, as data.

The machine-readable encoding of docs/FIRE_SAFETY_REFERENCE.md plus all of
Anton's German text (ITEM-001/026/027). Pure data + display helpers; depends on
nothing else in the app, so the rest of the program reads from here."""
from __future__ import annotations

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

