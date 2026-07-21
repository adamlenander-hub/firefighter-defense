"""Tests for the fire facts and Anton's text as data (content.py)

Split out of the old test_app.py (Step C)."""

import firefighter_defense as g
from helpers import *  # shared test builders/play-drivers

def test_classes_display_distinct_icons_and_fields():
    disp = g.classes_display()
    icons = [c["icon"] for c in disp]
    assert len(set(icons)) == len(icons)  # each class tellable apart by icon alone
    assert all("colour" in c and "letter" in c for c in disp)


def test_tools_have_costs():
    disp = g.tools_display()
    assert all(t["cost"] > 0 for t in disp)
    assert g.tool_cost("water") > 0 and g.tool_cost("nope") == 0


def test_resolution_matches_the_matrix_for_every_pair():
    for cls, row in g.MATRIX.items():
        for tool, expected in row.items():
            # ITEM-041: a "weak" (acceptable) tool may need a second hit to fully
            # wear a fire down — a "good" (ideal) one still does it in the first.
            gs, extinguished, earned = _shot(tool, cls, max_shots=4)
            if expected in ("good", "weak"):
                assert extinguished, f"{tool} on {cls} ({expected}) should put it out"
                assert earned == g.EXTINGUISH_REWARD + (g.SMART_BONUS if expected == "good" else 0)
            elif expected == "danger":
                assert not extinguished, f"{tool} on {cls} is dangerous — must NOT put it out"
                assert earned == 0
                assert gs.stats["danger_hits"] >= 1
            else:  # useless
                assert not extinguished, f"{tool} on {cls} is useless — must NOT put it out"
                assert earned == 0
                assert gs.stats["useless_hits"] >= 1


# --- ITEM-011 / ITEM-012: meet-the-fire cards + wrong-tool feedback ----------

def test_every_class_has_a_card():
    for c in g.FIRE_CLASSES:
        assert g.CLASS_CARDS.get(c["id"], "").strip(), f"{c['id']} has no meet-the-fire card"


def test_classes_display_includes_card_and_right_tool():
    for d in g.classes_display():
        assert d["card_de"].strip()
        assert d["right_tool_de"].strip()


def test_feedback_none_for_correct_tools():
    assert g.feedback_reason("A", "water") is None      # good
    assert g.feedback_reason("A", "co2") is None         # weak (still fine) -> no scolding


def test_feedback_danger_explains_and_suggests():
    msg = g.feedback_reason("electrical", "water")
    assert msg and "Strom" in msg                       # the danger reason
    assert g.right_tool_de("electrical") in msg          # suggests a correct tool
    fmsg = g.feedback_reason("F", "water")
    assert fmsg and ("Fett" in fmsg or "Stichflamme" in fmsg)


def test_feedback_useless_nudges_to_right_tool():
    msg = g.feedback_reason("F", "powder")               # powder on cooking oil = useless
    assert msg and g.right_tool_de("F") in msg           # names the wet-chemical extinguisher


def test_right_tool_is_actually_good():
    for c in g.FIRE_CLASSES:
        rt = g.right_tool_de(c["id"])
        # find the tool id whose German name is rt, and confirm it's 'good'
        tid = next(t["id"] for t in g.TOOLS if t["name_de"] == rt)
        assert g.MATRIX[c["id"]][tid] == "good"


def test_library_vignette_is_the_finds_his_name_beat():
    cap = g.vignette_de("bibliothek")["caption"]
    assert "Name" in cap or "name" in cap
    assert "Anton" in cap


def test_finale_delivers_the_closing_message():
    fin = g.finale_de()
    assert fin.get("scene") == "helmet"
    assert len(fin.get("lines", [])) >= 3
    blob = " ".join(fin["lines"])
    # courage, compassion and community matter more than equipment
    assert "Mut" in blob and "Mitgefühl" in blob and "Zusammenhalt" in blob
    assert "Ausrüstung" in blob
    # the helmet (Feuerwehrmütze) hand-over is present
    assert "Feuerwehrmütze" in fin.get("caption", "")
