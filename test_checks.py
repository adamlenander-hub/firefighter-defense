"""Tests for the self-checks: content / levels / narration / behaviour (checks.py)

Split out of the old test_app.py (Step C)."""

import firefighter_defense as g
from helpers import *  # shared test builders/play-drivers

def test_content_check_passes_on_good_data(tmp_path):
    db = str(tmp_path / "c.db")
    ok, problems = g.check_content(db)
    assert ok, f"expected a clean check, got: {problems}"


def test_check_fails_when_a_safety_fact_is_wrong(tmp_path, monkeypatch):
    # Flip a safety-critical square to a dangerous mistake and confirm the check
    # catches it with a clear message (rather than silently teaching it).
    broken = {cid: dict(row) for cid, row in g.MATRIX.items()}
    broken["electrical"]["water"] = "good"
    # build_content (in db.py) reads the matrix when it writes the database, so patch
    # it there — that's the value check_content ends up validating against the facts.
    monkeypatch.setattr("db.MATRIX", broken)
    db = str(tmp_path / "broken.db")
    ok, problems = g.check_content(db)
    assert not ok
    assert any("SAFETY FACT WRONG" in p and "electrical" in p for p in problems)


# --- Layout: build spots must never overlap the path -------------------------

def test_build_spots_clear_the_path():
    ok, problems = g.check_levels()
    assert ok, "build spots overlap the path: " + "; ".join(problems)


def test_check_levels_catches_a_spot_on_the_path(monkeypatch):
    lv = dict(g.LEVELS[0])
    lv["build_spots"] = [list(lv["path"][1])]      # a spot sitting exactly on a path point
    # check_levels (in checks.py) reads LEVELS from its own module, so patch it there.
    monkeypatch.setattr("checks.LEVELS", [lv])
    ok, problems = g.check_levels()
    assert not ok and problems


def test_behaviour_check_passes_on_the_shipped_level():
    ok, problems = g.behaviour_check()
    assert ok, "the shipped first level should only be won by safe play: " + "; ".join(problems)


def test_second_level_won_by_a_correct_mix():
    # ITEM-040: uses _play_out (not a one-shot buy) so a tower that runs out of
    # charge partway through gets noticed and re-bought, same as a real safe player.
    r = g._play_out(g.LEVELS[1], [(0, "powder"), (2, "wetchem")])
    assert r["status"] == "won" and r["leaked"] == 0


def test_new_missions_only_won_by_safe_play():
    # behaviour_check now plays each new mission; this asserts it stays green.
    ok, problems = g.behaviour_check()
    assert ok, "; ".join(problems)


def test_narration_guard_passes_on_shipped_hints():
    ok, problems = g.check_narration()
    assert ok, "; ".join(problems)


def test_narration_guard_catches_a_dangerous_recommendation(monkeypatch):
    # Flip a hint to positively recommend a dangerous tool and confirm it's caught.
    bad = {k: dict(v) for k, v in g.ANTON["missions"].items()}
    bad["bibliothek"] = dict(bad["bibliothek"])
    bad["bibliothek"]["hint"] = g.L("Nimm einfach Wasser auf die alte Leitung.")
    monkeypatch.setitem(g.ANTON, "missions", bad)
    ok, problems = g.check_narration()
    assert not ok
    assert any("bibliothek" in p and "water" in p for p in problems)


def test_arc_and_finale_do_not_change_any_fire_fact_or_level():
    # ITEM-028 is narrative only: the matrix and every level's waves/budget/lives are
    # untouched, and the safe-play guard still holds.
    ok, problems = g.check_content()
    assert ok, problems
    ok2, problems2 = g.behaviour_check()
    assert ok2, "; ".join(problems2)


def test_visual_reskin_changed_no_fire_fact_or_balance():
    # ITEM-038 is visual only — the matrix and safe-play guards are unchanged.
    ok, problems = g.check_content()
    assert ok, problems
    ok2, problems2 = g.behaviour_check()
    assert ok2, "; ".join(problems2)


def test_fire_characters_changed_no_fire_fact_or_balance():
    ok, problems = g.check_content()
    assert ok, problems
    ok2, problems2 = g.behaviour_check()
    assert ok2, "; ".join(problems2)


def test_path_bg_palette_changes_touch_no_fire_fact_or_balance():
    ok, problems = g.check_content()
    assert ok, problems
    ok2, problems2 = g.behaviour_check()
    assert ok2, "; ".join(problems2)


def test_landscape_layout_is_visual_only_no_content_or_balance_regression():
    # ITEM-053 is pure layout — the fire-safety content and safe-play guard must
    # still be exactly as green as before this change.
    ok, problems = g.check_content()
    assert ok, problems
    ok2, problems2 = g.behaviour_check()
    assert ok2, "; ".join(problems2)


def test_version_a_is_visual_only_no_content_or_balance_regression():
    # ITEM-057 is layout/overlay only — content and safe-play guard stay green.
    ok, problems = g.check_content()
    assert ok, problems
    ok2, problems2 = g.behaviour_check()
    assert ok2, "; ".join(problems2)
