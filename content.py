"""The fire facts and every line Anton speaks — the teaching content, as data.

The machine-readable encoding of docs/FIRE_SAFETY_REFERENCE.md plus all of
Anton's German text (ITEM-001/026/027). Pure data + display helpers; depends on
nothing else in the app, so the rest of the program reads from here."""
from __future__ import annotations

# --- Language helpers (ITEM: German→English in-game switch) -------------------
# The game is German-first; English is added beside every player-visible German
# field. These two tiny helpers pick the right language, always falling back to
# German so a (guarded-against) missing English string can never crash a render.

def _by_lang(de, en, lang: str = "de"):
    """Pick the English value when lang=='en' and it exists, else the German."""
    if lang == "en" and en:
        return en
    return de


def _pick(node, lang: str = "de") -> str:
    """Pick a language string out of an L(...) node ({'de':.., 'en':..})."""
    if not isinstance(node, dict):
        return ""
    if lang == "en":
        en = node.get("en")
        if en:
            return en
    return node.get("de", "")

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
    {"id": "A", "name_de": "Brandklasse A", "name_en": "Class A",
     "examples_de": "Holz, Papier, Textilien, Fachwerk",
     "examples_en": "Wood, paper, textiles, timber framing", "icon": "🪵",
     "colour": "#a16207", "note_de": None, "note_en": None},
    {"id": "B", "name_de": "Brandklasse B", "name_en": "Class B",
     "examples_de": "Benzin, Öl, Farbe, Spiritus",
     "examples_en": "Petrol, oil, paint, spirits", "icon": "🛢️",
     "colour": "#7c3aed", "note_de": None, "note_en": None},
    {"id": "C", "name_de": "Brandklasse C", "name_en": "Class C",
     "examples_de": "Propan, Butan, Erdgas",
     "examples_en": "Propane, butane, natural gas", "icon": "💨",
     "colour": "#0d9488", "note_de": "Zuerst die Gaszufuhr absperren.",
     "note_en": "Turn off the gas supply first."},
    {"id": "electrical", "name_de": "Elektrobrand", "name_en": "Electrical fire",
     "examples_de": "Verteiler, Ladegeräte, Geräte unter Spannung",
     "examples_en": "Distribution boards, chargers, appliances under power", "icon": "⚡",
     "colour": "#2563eb", "note_de": "Wenn möglich zuerst den Strom abschalten.",
     "note_en": "If possible, switch off the power first."},
    {"id": "D", "name_de": "Brandklasse D", "name_en": "Class D",
     "examples_de": "Magnesium, Aluminium, Lithium",
     "examples_en": "Magnesium, aluminium, lithium", "icon": "🔩",
     "colour": "#64748b", "note_de": None, "note_en": None},
    {"id": "F", "name_de": "Brandklasse F", "name_en": "Class F",
     "examples_de": "Fritteuse, Fettbrand",
     "examples_en": "Deep-fat fryer, grease fire", "icon": "🍳",
     "colour": "#db2777", "note_de": None, "note_en": None},
]


def classes_display(lang: str = "de") -> list:
    """Display info per fire class for the browser (id, name, icon, colour, letter).
    Framework-free so it can be tested and served without a server.

    The KEYS are unchanged (name_de/card_de/right_tool_de) so the default (German)
    response is byte-identical; only the VALUES switch language when lang=='en'."""
    letters = {"A": "A", "B": "B", "C": "C", "electrical": "E", "D": "D", "F": "F"}
    return [
        {"id": c["id"], "name_de": _by_lang(c["name_de"], c.get("name_en"), lang),
         "icon": c["icon"],
         "colour": c["colour"], "letter": letters.get(c["id"], c["id"][:1].upper()),
         "card_de": _by_lang(CLASS_CARDS.get(c["id"], ""), CLASS_CARDS_EN.get(c["id"], ""), lang),
         "right_tool_de": right_tool_de(c["id"], lang)}
        for c in FIRE_CLASSES
    ]

# Extinguisher tools (the towers). Fire blanket is a special item added later.
# "cost" is what it takes to place one (ITEM-009); "short" + "hex" are for drawing
# the tower and the tool palette.
TOOLS = [
    {"id": "water", "name_de": "Wasser", "name_en": "Water", "colour_de": "Rot", "cost": 40, "short": "H₂O", "short_en": "H₂O", "hex": "#0284c7"},
    {"id": "foam", "name_de": "Schaum", "name_en": "Foam", "colour_de": "Creme", "cost": 60, "short": "Schaum", "short_en": "Foam", "hex": "#d97706"},
    {"id": "co2", "name_de": "Kohlendioxid (CO₂)", "name_en": "Carbon dioxide (CO₂)", "colour_de": "Schwarz", "cost": 80, "short": "CO₂", "short_en": "CO₂", "hex": "#1f2937"},
    {"id": "powder", "name_de": "Pulver (ABC)", "name_en": "Dry powder (ABC)", "colour_de": "Blau", "cost": 70, "short": "Pulver", "short_en": "Powder", "hex": "#4d7c0f"},
    {"id": "wetchem", "name_de": "Fettbrandlöscher", "name_en": "Wet chemical (class F)", "colour_de": "Gelb", "cost": 80, "short": "Fett", "short_en": "Wet", "hex": "#be123c"},
    {"id": "metal", "name_de": "Metallbrandpulver", "name_en": "Specialist metal powder (class D)", "colour_de": "—", "cost": 120, "short": "Metall", "short_en": "Metal", "hex": "#57534e"},
]


def tools_display(lang: str = "de") -> list:
    """Tool info for the browser (palette + drawing towers): id, name, cost, short
    label, colour. Framework-free. Keys unchanged (name_de/short) — values switch."""
    return [
        {"id": t["id"], "name_de": _by_lang(t["name_de"], t.get("name_en"), lang),
         "cost": t["cost"],
         "short": _by_lang(t["short"], t.get("short_en"), lang), "hex": t["hex"]}
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
        "A": L("Holz, Papier, Stoff — ein ganz gewöhnliches Feuer. Keine Sorge: Wasser, Schaum oder Pulver löschen es sicher. (Ich halte beim Wasser nur lieber etwas Abstand …)",
               "Wood, paper, cloth — a perfectly ordinary fire. No worries: water, foam or powder put it out safely. (I just prefer to keep my distance from the water …)"),
        "B": L("Brennende Flüssigkeit! Kein Wasser, das spritzt nur. Schaum, Pulver oder CO₂ ersticken die Flammen.",
               "Burning liquid! No water — it only splashes about. Foam, powder or CO₂ smother the flames."),
        "C": L("Brennendes Gas. Wenn möglich zuerst die Gaszufuhr absperren! Pulver hält die Flamme in Schach.",
               "Burning gas. If you can, shut off the gas supply first! Powder keeps the flame in check."),
        "electrical": L("Da steht etwas unter Strom. Bloß kein Wasser — Stromschlag! Am besten CO₂ (und den Strom abschalten).",
               "Something is live with electricity. Absolutely no water — electric shock! CO₂ is best (and switch off the power)."),
        "D": L("Brennendes Metall — heikel. Nur das Spezial-Metallbrandpulver hilft. Wasser wäre gefährlich.",
               "Burning metal — tricky. Only the special metal-fire powder helps. Water would be dangerous."),
        "F": L("Fett in der Fritteuse brennt. NIE Wasser — das gibt eine Stichflamme! Der Fettbrandlöscher hilft.",
               "Fat in the fryer is burning. NEVER water — it throws a fireball! The wet-chemical extinguisher is the one."),
    },
    # --- Wrong-tool feedback (ITEM-012). Danger reasons keyed "class|tool"; the
    #     glue templates build the kind, never-scolding one-liner around them.
    "danger_reasons": {
        "F|water": L("Wasser im Fettbrand führt zur Fettexplosion (Stichflamme).",
                     "Water in a fat fire causes a fat explosion (a fireball)."),
        "electrical|water": L("Wasser leitet Strom – Stromschlaggefahr.",
                     "Water conducts electricity – risk of electric shock."),
        "electrical|foam": L("Schaum leitet Strom – nicht auf Spannung.",
                     "Foam conducts electricity – not on live equipment."),
        "electrical|wetchem": L("Fettbrandlöscher leitet Strom – nicht auf Elektrobrand.",
                     "The wet-chemical extinguisher conducts electricity – not on an electrical fire."),
        "D|water": L("Wasser auf brennendem Metall reagiert heftig.",
                     "Water on burning metal reacts violently."),
        "D|foam": L("Wasserbasiertes Mittel auf Metall reagiert heftig.",
                     "A water-based agent on metal reacts violently."),
        "D|wetchem": L("Wasserbasiertes Mittel auf Metall reagiert heftig.",
                     "A water-based agent on metal reacts violently."),
        "B|water": L("Wasser verteilt die brennende Flüssigkeit.",
                     "Water spreads the burning liquid around."),
        "F|foam": L("Wasserbasiertes Mittel im Fettbrand – Stichflammengefahr.",
                     "A water-based agent in a fat fire – risk of a fireball."),
        "F|co2": L("CO₂ kann brennendes Fett wegschleudern.",
                     "CO₂ can blast burning fat out of the pan."),
    },
    "feedback": {
        "danger_fallback": L("Das macht es nur schlimmer!", "That only makes it worse!"),
        "danger_suffix": L(" Nimm lieber {tool}.", " Better use {tool}."),
        "useless": L("Das wirkt hier leider nicht.", "That has no effect here."),
        "useless_suffix": L(" Nimm {tool}.", " Use {tool}."),
    },
    # --- Supply-hazard warnings (ITEM-016): shown when a fire is sprayed before its
    #     gas/power supply is cut.
    "hazard_warn": {
        "gas": L("Bei Gasbränden zuerst die Gaszufuhr absperren!",
                 "For gas fires, shut off the gas supply first!"),
        "power": L("Bei Elektrobränden zuerst den Strom abschalten!",
                 "For electrical fires, switch off the power first!"),
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
            "open": L("Riechst du das? Rauch zieht durch die Fachwerkgasse. Ich, Anton, spüre so etwas immer zuerst — hier bricht gleich Feuer aus. Schnell, die Wehr braucht dich!",
                "Do you smell that? Smoke is drifting through the half-timbered lane. I, Anton, always sense these things first — fire is about to break out here. Quick, the brigade needs you!"),
            "anecdote": L("Diese Gasse kenne ich seit 150 Jahren. Vor achtzig Jahren sprang hier schon einmal ein Funke von Balken zu Balken — die halbe Nachbarschaft stand mit Eimern bereit. In dem Haus dort wohnt ein altes Ehepaar, das Andenken an unsere Feuerwehr hütet. Die beschützen wir heute.",
                "I've known this lane for 150 years. Eighty years ago a spark once leapt from beam to beam here — half the neighbourhood stood ready with buckets. In that house lives an old couple who keep mementos of our fire brigade. Today we protect them."),
            "hint": L("Aus der Backstube kriechen Fettbrände — die brauchen ihren eigenen Löscher, niemals Wasser. Auf Holz und Strom ist das ABC-Pulver ein guter Freund, aber bloß kein Wasser auf die Leitung!",
                "Grease fires creep out of the bakery — they need their own extinguisher, never water. On wood and live wiring the ABC powder is a good friend, but never any water on the line!"),
            "close": L("Geschafft! Die Balken halten, das Ehepaar ist sicher. Weißt du, jedes Mal, wenn ich unsere Wehr so arbeiten sehe, wird mir ganz warm ums Geisterherz. Auf zum nächsten Einsatz!",
                "Done it! The beams hold, the old couple is safe. You know, every time I watch our brigade work like this, it warms my old ghostly heart. On to the next call!"),
            "bonus": L("Rettungsbonus: Das alte Ehepaar und seine Andenken sind unversehrt.",
                "Rescue bonus: The old couple and their mementos are unharmed."),
        },
        "bibliothek": {
            "open": L("In meiner Burg — der Burgbibliothek! Ich spüre heiße Luft zwischen den Regalen. Eine alte Leitung glimmt und hat schon ein paar Bücher entzündet. Bitte, sei behutsam mit meinen Protokollen!",
                "In my castle — the castle library! I can feel hot air between the shelves. An old wire is smouldering and has already set a few books alight. Please, be gentle with my records!"),
            "anecdote": L("Hier lagern Einsatzprotokolle aus 150 Jahren. Vielleicht steht in einer dieser Kisten sogar mein eigener Name — der junge Burgwächter, der blieb. Nur: Wasser würde die alten Seiten für immer ruinieren. Am liebsten ist mir, wenn gar nichts auf die Papiere spritzt.",
                "Here lie duty logs from 150 years. Perhaps one of these boxes even holds my own name — the young castle watchman who stayed. Only: water would ruin the old pages forever. I like it best when nothing at all is sprayed on the papers."),
            "hint": L("Zuerst den Strom abschalten — das ist der sauberste Weg, ganz ohne Wasser auf den kostbaren Protokollen. Die brennenden Bücher sind ein gewöhnliches Feuer; nur die Leitung verträgt niemals Wasser.",
                "First switch off the power — that's the cleanest way, entirely without water on the precious records. The burning books are an ordinary fire; only the wiring never tolerates water."),
            "close": L("Der Strom ist aus, die Bücher gerettet — und kein Blatt ist nass geworden! Schau, hier … „Anton, treuer Wächter der Burg“. Zum ersten Mal seit 150 Jahren fühle ich mich wirklich gesehen. Danke, dass du meine Geschichte gerettet hast.",
                "The power is off, the books are saved — and not a single page got wet! Look, here … “Anton, faithful watchman of the castle.” For the first time in 150 years I truly feel seen. Thank you for saving my story."),
            "bonus": L("Rettungsbonus: Kein einziges Protokoll ist verloren gegangen.",
                "Rescue bonus: Not a single record was lost."),
        },
        "kurpark": {
            "open": L("Ein Unwetter über dem Kurpark! Bäume krachen, und mittendrin sitzen eingeschlossene Besucher fest. Ich höre ihre Angst — und die der Tiere. Halt die Wege frei, damit ihnen nichts geschieht!",
                "A storm over the spa park! Trees are crashing down, and trapped visitors are stuck right in the middle of it. I can hear their fear — and the animals' too. Keep the paths clear so no harm comes to them!"),
            "anecdote": L("Der Kurpark war immer der Stolz von Königstein — Kurkonzerte, Sonntagsspaziergänge, verliebte Paare unter den alten Bäumen. Heute peitscht der Sturm Funken über die Wege. Bring die Menschen sicher zum Kurhaus, so wie es unsere Wehr seit jeher tut.",
                "The spa park was always the pride of Königstein — spa concerts, Sunday strolls, sweethearts under the old trees. Today the storm whips sparks across the paths. Bring the people safely to the spa house, just as our brigade always has."),
            "hint": L("Der Sturm treibt allerlei Feuer über die Wege — halt die Besucher frei! ABC-Pulver ist dein Allrounder für Holz, Flüssiges und Strom. Aber die Fritteuse vom Imbiss und der Strom: niemals Wasser, und der Fettbrand will seinen eigenen Löscher.",
                "The storm drives all sorts of fire across the paths — keep the visitors clear! ABC powder is your all-rounder for wood, liquids and live wiring. But the snack-stall fryer and the wiring: never water, and the fat fire wants its own extinguisher."),
            "close": L("Der Sturm zieht ab, und alle Besucher sind wohlauf im Kurhaus. Dieses stille Dankeschön in ihren Augen — dafür lohnt sich alles. Zusammen sind wir stark, mein Freund.",
                "The storm moves on, and every visitor is safe and sound in the spa house. That quiet thank-you in their eyes — it makes everything worth it. Together we are strong, my friend."),
            "bonus": L("Rettungsbonus: Alle eingeschlossenen Besucher sind in Sicherheit.",
                "Rescue bonus: All the trapped visitors are safe."),
        },
        "feuerwerk": {
            "open": L("Das Jubiläumsfest! Und ausgerechnet jetzt kippt ein Feuerwerkskörper um und droht die Bühne zu entzünden. Ich liebe dieses Fest so sehr — bitte, rette die Bühne!",
                "The anniversary festival! And of all moments, now a firework topples over and threatens to set the stage alight. I love this festival so much — please, save the stage!"),
            "anecdote": L("150 Jahre Freiwillige Feuerwehr Königstein — heute feiert die ganze Stadt. Neben der Bühne stehen Sprit für die Effekte, Kabel für die Lichter und ein E-Scooter-Akku am Ladepunkt. Ein Funke genügt. Aber wenn eine Gemeinschaft zusammensteht, fürchte selbst ich mich weniger.",
                "150 years of the Königstein Volunteer Fire Brigade — today the whole town is celebrating. Beside the stage stand fuel for the effects, cables for the lights, and an e-scooter battery on charge. One spark is enough. But when a community stands together, even I am less afraid."),
            "hint": L("Am Bühnenrand mischen sich Sprit, Kabel und ein glühender Akku — ein heikles Trio! CO₂ bändigt Sprit und Kabel, sauber und ohne Rückstände. Den Akku zähmt nur das Metallbrandpulver; niemals Wasser hier.",
                "At the stage edge fuel, cables and a glowing battery all mix — a tricky trio! CO₂ tames the fuel and cables, cleanly and without residue. Only the metal powder tames the battery; never water here."),
            "close": L("Die Bühne steht, das Feuerwerk ist entschärft, und das Fest geht weiter! Sieh nur, wie alle zusammenhalten. Vielleicht … vielleicht bin ich ja doch ein kleiner Feuerwehrgeist. Danke, dass du an Königstein glaubst.",
                "The stage stands, the firework is made safe, and the festival goes on! Just look how everyone pulls together. Maybe … maybe I really am a little fire-brigade ghost after all. Thank you for believing in Königstein."),
            "bonus": L("Rettungsbonus: Bühne und Festgäste sind unversehrt.",
                "Rescue bonus: The stage and the festival guests are unharmed."),
        },
    },
    # --- Anton's growth arc (ITEM-028) -------------------------------------------
    # His courage as the campaign progresses, indexed by the number of story missions
    # completed (0..4). Shown as a small mood line; his drawn ghost also stands taller,
    # more solid and a touch brighter with each mission (in the browser).
    "arc": {
        "courage": [
            L("Ich bin nur ein scheuer Burggeist … aber ich versuche, mutig zu sein. Bleib bei mir.",
              "I'm only a shy castle ghost … but I'm trying to be brave. Stay with me."),
            L("Schon ein Einsatz geschafft — mein altes Geisterherz klopft ein bisschen mutiger.",
              "One call already handled — my old ghostly heart is beating a little braver."),
            L("Zwei Einsätze! Weißt du, langsam traue ich mich sogar näher ans Feuer heran.",
              "Two calls! You know, I'm slowly daring to move closer to the fire."),
            L("Drei gemeistert — ich flüstere nicht mehr nur, ich rufe fast schon Kommandos!",
              "Three mastered — I'm not only whispering any more, I'm almost calling out commands!"),
            L("Alle Einsätze gemeistert. Ich stehe aufrecht und stolz — fast wie ein echter Feuerwehrgeist.",
              "Every call mastered. I stand upright and proud — almost like a real fire-brigade ghost."),
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
            "title": L("Nachbarn in der Nacht", "Neighbours in the Night"),
            "scene": "lantern",
            "caption": L("Vor langer Zeit, so erzählt man sich, reichten sich Nachbarn in einer engen Gasse eimerweise Wasser weiter, bis der letzte Funke erlosch. Kein Name ist geblieben — nur der Mut, füreinander dazustehen.",
                "Long ago, so the story goes, neighbours in a narrow lane passed buckets of water hand to hand until the last spark died. No name remains — only the courage to stand by one another."),
        },
        "bibliothek": {
            "title": L("Ein Name im Protokoll", "A Name in the Log"),
            "scene": "records",
            "caption": L("Zwischen den vergilbten Zeilen entdeckt Anton eine Eintragung, die klingt wie sein eigener Name. „Da … das könnte ich sein.“ Zum ersten Mal seit 150 Jahren fühlt er sich wahrhaftig gesehen.",
                "Among the yellowed lines Anton discovers an entry that sounds like his own name. “There … that could be me.” For the first time in 150 years he feels truly seen."),
        },
        "kurpark": {
            "title": L("Nach dem Sturm", "After the Storm"),
            "scene": "storm",
            "caption": L("Als das Unwetter sich legte, standen die Menschen im Kurpark noch lange beieinander — durchnässt, erleichtert, dankbar. So war es wohl schon immer: Gemeinschaft hält jedem Sturm stand.",
                "When the storm had passed, the people in the spa park stood together a long while — soaked, relieved, grateful. So it has always been: community withstands any storm."),
        },
        "feuerwerk": {
            "title": L("150 Jahre Licht", "150 Years of Light"),
            "scene": "festival",
            "caption": L("Über der Festbühne steigen Funken in den Nachthimmel. Anderthalb Jahrhunderte lang hat diese Stadt zusammengehalten — und Anton ist bei jedem Fest, jeder Sorge, jedem Jubel mitgeschwebt.",
                "Above the festival stage sparks rise into the night sky. For a century and a half this town has held together — and Anton has drifted along through every celebration, every worry, every cheer."),
        },
    },
    # --- The finale (ITEM-028) ---------------------------------------------------
    # Plays once, when ALL four missions are complete: the community gives Anton a
    # little fire helmet (he wears it from now on) and the closing message lands in
    # plain words — courage, compassion and community matter more than any equipment.
    "finale": {
        "title": L("Zum Feuerwehrgeist ernannt", "Named a Fire-Brigade Ghost"),
        "scene": "helmet",
        "caption": L("Die ganze Gemeinschaft versammelt sich und setzt Anton eine kleine Feuerwehrmütze auf.",
            "The whole community gathers and places a little fire helmet on Anton."),
        "lines": [
            L("Anton, du hast keinen Schlauch gehalten und keinen Tropfen Wasser berührt — und doch warst du bei jedem Einsatz dabei.",
              "Anton, you never held a hose and never touched a drop of water — and yet you were there for every single call."),
            L("Du hast gewittert, gewarnt, Mut gemacht und Menschen verbunden. Genau das macht einen Feuerwehrgeist aus.",
              "You sensed danger, you warned, you gave courage and you brought people together. That is exactly what makes a fire-brigade ghost."),
            L("Mut, Mitgefühl und Zusammenhalt zählen mehr als jede Ausrüstung. Die Mütze ist nur das Zeichen für das, was du längst bist.",
              "Courage, compassion and community matter more than any equipment. The helmet is only the sign of what you have long been."),
            L("Zum Einsatz, VOR! — von nun an für immer als Feuerwehrgeist von Königstein.",
              "To the call, forward! — from now on, forever the fire-brigade ghost of Königstein."),
        ],
    },
}


def anton_de(path: tuple, lang: str = "de") -> str:
    """Read one of Anton's lines by its path in ANTON, e.g.
    anton_de(("missions", "fachwerk", "open")). Returns '' if not present, so a
    missing line can never crash a render. Defaults to German (byte-identical to
    before); pass lang='en' for the English slot."""
    node = ANTON
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return ""
        node = node[key]
    return _pick(node, lang) if isinstance(node, dict) else ""


def mission_lines_de(key: str, lang: str = "de") -> dict:
    """Anton's per-mission framing (open/anecdote/hint/close/bonus) as plain strings
    for the browser. Empty dict if the mission has no framing."""
    m = ANTON["missions"].get(key)
    if not m:
        return {}
    return {field: _pick(line, lang) for field, line in m.items()}


def vignette_de(key: str, lang: str = "de") -> dict:
    """A mission's reward vignette (ITEM-028): {title, scene, caption}, or {} if
    none. 'scene' is a lightweight canvas-animation id the browser draws."""
    v = ANTON.get("vignettes", {}).get(key)
    if not v:
        return {}
    return {"title": _pick(v["title"], lang), "scene": v["scene"], "caption": _pick(v["caption"], lang)}


def anton_arc_de(lang: str = "de") -> list:
    """Anton's courage lines by missions-completed (0..N) (ITEM-028)."""
    return [_pick(line, lang) for line in ANTON.get("arc", {}).get("courage", [])]


def finale_de(lang: str = "de") -> dict:
    """The campaign finale (ITEM-028): {title, scene, caption, lines[]}."""
    f = ANTON.get("finale", {})
    if not f:
        return {}
    return {
        "title": _pick(f.get("title", {}), lang),
        "scene": f.get("scene", ""),
        "caption": _pick(f.get("caption", {}), lang),
        "lines": [_pick(line, lang) for line in f.get("lines", [])],
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
CLASS_CARDS_EN = {cid: (line.get("en") or "") for cid, line in ANTON["class_cards"].items()}


# --- Supply-hazard mechanic (ITEM-016) ---------------------------------------
# Some fires can't just be sprayed — the supply feeding them must be cut off first.
# A level opts in via "supplies": ["gas", "power"]. In such a level, spraying that
# kind of fire while its supply is on does nothing (Anton says cut the supply first);
# cutting the supply puts those fires out. Level 1 declares no supplies, so it keeps
# its original "use the right extinguisher" behaviour for electrical fires.
HAZARD_CLASS = {"gas": "C", "power": "electrical"}
HAZARD_ACTION_DE = {"gas": "Gaszufuhr absperren", "power": "Strom abschalten"}
HAZARD_ACTION_EN = {"gas": "Shut off the gas supply", "power": "Switch off the power"}
HAZARD_BUTTON_DE = {"gas": "🔧 Gas absperren", "power": "⚡ Strom abschalten"}
HAZARD_BUTTON_EN = {"gas": "🔧 Shut off gas", "power": "⚡ Switch off power"}
HAZARD_WARN_DE = {h: line["de"] for h, line in ANTON["hazard_warn"].items()}
HAZARD_WARN_EN = {h: (line.get("en") or "") for h, line in ANTON["hazard_warn"].items()}


def right_tool_de(class_id: str, lang: str = "de") -> str:
    """The name of a correct (good) tool for a class, for suggestions. '' if none."""
    row = MATRIX.get(class_id, {})
    for t in TOOLS:
        if row.get(t["id"]) == "good":
            return _by_lang(t["name_de"], t.get("name_en"), lang)
    return ""


def right_action_de(class_id: str, supplies=None, lang: str = "de") -> str:
    """The correct action for a class, given a level's supply hazards. If the class
    is fed by a cut-able supply in this level (gas/power), the right action is cutting
    that supply; otherwise it's the right extinguisher."""
    for hazard in (supplies or []):
        if HAZARD_CLASS.get(hazard) == class_id:
            return (HAZARD_ACTION_EN if lang == "en" else HAZARD_ACTION_DE)[hazard]
    return right_tool_de(class_id, lang)


def feedback_reason(class_id: str, tool_id: str, lang: str = "de") -> str | None:
    """A short, kind, Anton-voice message for a wrong shot (ITEM-012), or None when
    the tool is fine. Dangerous shots explain the danger; useless shots nudge toward
    the right tool. Facts from the reference."""
    outcome = MATRIX.get(class_id, {}).get(tool_id)
    right = right_tool_de(class_id, lang)
    if outcome == "danger":
        node = ANTON["danger_reasons"].get(f"{class_id}|{tool_id}")
        why = _pick(node, lang) if node else _pick(ANTON["feedback"]["danger_fallback"], lang)
        suffix = _pick(ANTON["feedback"]["danger_suffix"], lang)
        return why + (suffix.format(tool=right) if right else "")
    if outcome == "useless":
        base = _pick(ANTON["feedback"]["useless"], lang)
        suffix = _pick(ANTON["feedback"]["useless_suffix"], lang)
        return base + (suffix.format(tool=right) if right else "")
    return None

