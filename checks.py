"""The self-checks — the project's \"proof not claims\" guards.

check_content (facts match the reference), check_levels (build spots clear the
path), check_narration (Anton's hints point to the right action), and
behaviour_check (the first level is only won by safe, correct play). All
framework-free so they run in CI and the pre-save hook."""
from __future__ import annotations

import sqlite3
from contextlib import closing

from config import *
from content import *
from db import *
from levels import *
from engine import *

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

# English equivalents (German→English switch). Same ordering discipline: the
# multi-word "metal powder" phrase is listed under "metal" and blanked BEFORE the
# bare "powder" keyword is tested, so "the metal powder" is never misread as a
# recommendation of ABC powder. English matching is case-insensitive (hints mix
# "CO₂", "ABC powder", lower-case "water"), so both keywords and the working text
# are lower-cased before comparison.
TOOL_KEYWORDS_EN = [
    ("co2", ["co₂", "carbon dioxide"]),
    ("wetchem", ["wet chemical", "wet-chemical"]),
    ("foam", ["foam"]),
    ("water", ["water"]),
    ("metal", ["specialist metal powder", "metal-fire powder", "metal powder", "metal"]),
    ("powder", ["abc powder", "dry powder", "powder"]),
]
# English negation cues, matched on WORD BOUNDARIES so "another" is not read as "no"
# and "cannot" is not read as "not" spuriously — a clause naming a tool alongside one
# of these is a warning ("never water"), not a recommendation.
NEGATION_CUES_EN = ["no", "not", "never", "without", "instead", "avoid", "away from"]


def _hint_recommendation_problems(key, hint, danger_tools, good_tools,
                                  keywords, negation_cues, boundary):
    """Scan one mission HINT for a tool RECOMMENDATION (a named tool with no negation
    cue in its clause) that is dangerous or not-correct for the mission's fires.
    `boundary` selects the English behaviour (case-insensitive keywords + word-boundary
    negation); when False the original German (case-sensitive, substring) behaviour is
    used exactly, so the German guard is byte-for-byte unchanged."""
    import re
    problems: list[str] = []
    for clause in re.split(r"[,.;:!?—\n]", hint):
        if not clause.strip():
            continue
        low = clause.lower()
        if boundary:
            negated = any(re.search(r"\b" + re.escape(cue) + r"\b", low) for cue in negation_cues)
            work = low                      # match keywords case-insensitively
        else:
            negated = any(cue in low for cue in negation_cues)
            work = clause                   # original German behaviour (case-sensitive)
        for tid, kws in keywords:
            named = any(kw in work for kw in kws)
            if not named:
                continue
            # Blank this tool's matched words so a later tool (e.g. "powder" inside
            # "metal powder") can't get a false positive from the same clause.
            for kw in kws:
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
    return problems


def check_narration() -> tuple[bool, list]:
    """Guard Anton's free prose (ITEM-026). The fire-tool matrix is already checked
    against the reference; his anecdotes and hints are prose the matrix can't cover.

    The rule: a mission's in-play HINT must never name a tool that is DANGEROUS on one
    of that mission's fires as the thing to USE. A tool named in a hint clause that has
    no negation cue is treated as a recommendation and must be (a) a correct ('good')
    tool for at least one of the mission's fire classes and (b) never 'danger' for any
    of them. Dangerous tools may still appear in the hint under a warning ("nie Wasser").
    This now guards BOTH languages (German→English switch), so an English
    mistranslation can't silently recommend a dangerous tool either.
    Framework-free, so it runs with --check-content."""
    problems: list[str] = []

    langs = (
        ("de", TOOL_KEYWORDS, NEGATION_CUES, False),
        ("en", TOOL_KEYWORDS_EN, NEGATION_CUES_EN, True),
    )
    for lv in LEVELS:
        if not lv.get("campaign"):
            continue
        key = lv.get("key", "")
        classes = set()
        for w in lv.get("waves", []):
            classes.update(w.get("fires", []))
        danger_tools = {tid for cid in classes for tid in (t["id"] for t in TOOLS)
                        if MATRIX.get(cid, {}).get(tid) == "danger"}
        good_tools = {tid for cid in classes for tid in (t["id"] for t in TOOLS)
                      if MATRIX.get(cid, {}).get(tid) == "good"}
        for lang, keywords, negation_cues, boundary in langs:
            hint = anton_de(("missions", key, "hint"), lang)
            if not hint:
                problems.append(f"Campaign mission '{key}' is missing Anton's {lang} in-play hint.")
                continue
            problems.extend(_hint_recommendation_problems(
                key, hint, danger_tools, good_tools, keywords, negation_cues, boundary))
    return (len(problems) == 0, problems)


def check_english_content() -> tuple[bool, list]:
    """Confirm the English translation is COMPLETE and its safety headlines survive.

    Checks that every player-visible German field has an English counterpart (fire
    classes, tools, ALL of Anton's lines, every level's name/place/building), re-asserts
    the reference's headline lessons still land in English (water on a fat fire, water
    on an electrical fire, cut-the-gas-first), and runs the English narration guard so a
    mistranslation can't quietly recommend a dangerous tool. Framework-free."""
    problems: list[str] = []

    # 1. Fire classes: name + examples always; note only where a German note exists.
    for c in FIRE_CLASSES:
        if not (c.get("name_en") or "").strip():
            problems.append(f"Fire class {c['id']} is missing name_en.")
        if not (c.get("examples_en") or "").strip():
            problems.append(f"Fire class {c['id']} is missing examples_en.")
        if c.get("note_de") and not (c.get("note_en") or "").strip():
            problems.append(f"Fire class {c['id']} is missing note_en.")

    # 2. Tools: name + short label.
    for t in TOOLS:
        if not (t.get("name_en") or "").strip():
            problems.append(f"Tool {t['id']} is missing name_en.")
        if not (t.get("short_en") or "").strip():
            problems.append(f"Tool {t['id']} is missing short_en.")

    # 3. Every one of Anton's lines (an L-node has both 'de' and 'en' keys).
    def _walk(node, path):
        if isinstance(node, dict):
            if "de" in node and "en" in node:      # an L(...) node
                if not (node.get("en") or "").strip():
                    problems.append("Anton line missing English: " + "/".join(path))
                return
            for k, v in node.items():
                _walk(v, path + [str(k)])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                _walk(v, path + [str(i)])
    _walk(ANTON, ["ANTON"])

    # 4. Every level's player-visible text.
    for i, lv in enumerate(LEVELS):
        if not (lv.get("name_en") or "").strip():
            problems.append(f"Level {i} ('{lv.get('key')}') is missing name_en.")
        if not (lv.get("place_en") or "").strip():
            problems.append(f"Level {i} ('{lv.get('key')}') is missing place_en.")
        if not ((lv.get("building") or {}).get("name_en") or "").strip():
            problems.append(f"Level {i} ('{lv.get('key')}') building is missing name_en.")

    # 5. Safety headlines must survive in English.
    fat = (feedback_reason("F", "water", "en") or "").lower()
    if "fireball" not in fat:
        problems.append("English safety headline lost: water on a fat fire must warn of a fireball.")
    elec = (feedback_reason("electrical", "water", "en") or "").lower()
    if "electric shock" not in elec:
        problems.append("English safety headline lost: water on an electrical fire must warn of electric shock.")
    c_note = next((c.get("note_en") or "" for c in FIRE_CLASSES if c["id"] == "C"), "")
    gas = (HAZARD_WARN_EN.get("gas", "") + " " + c_note).lower()
    if "gas supply" not in gas:
        problems.append("English safety headline lost: gas fires must say to shut off the gas supply first.")

    # 6. The English narration guard (also covers German — belt and braces here).
    ok_narr, narr = check_narration()
    if not ok_narr:
        problems.extend(narr)

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

