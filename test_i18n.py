"""Tests for the German→English in-game language switch.

Covers: English completeness (classes / tools / levels / all Anton lines), the
accessors' default-de-vs-en behaviour, the langToggle control in the page, the
/api/*?lang=en responses via a TestClient (with default == ?lang=de byte-identity),
and the English narration safety guard (including a deliberately dangerous English
mistranslation being caught)."""

import pytest

import firefighter_defense as g


# The API routes are thin wrappers over framework-free payload builders (web.py),
# so the ?lang plumbing is exercised directly here — the sandbox's pytest runner has
# no FastAPI installed (the suite runs against conftest's stand-in). A parallel set of
# tests below drives the SAME routes through a real TestClient, skipped automatically
# when FastAPI/httpx aren't importable, so they run wherever the web stack is present.


# --- English completeness -----------------------------------------------------

def test_every_class_has_english_name_examples_and_notes():
    for c in g.FIRE_CLASSES:
        assert (c.get("name_en") or "").strip(), c["id"]
        assert (c.get("examples_en") or "").strip(), c["id"]
        if c.get("note_de"):                      # a note only needs English if it has German
            assert (c.get("note_en") or "").strip(), c["id"]


def test_every_tool_has_english_name_and_short():
    for t in g.TOOLS:
        assert (t.get("name_en") or "").strip(), t["id"]
        assert (t.get("short_en") or "").strip(), t["id"]


def test_every_level_has_english_name_place_and_building():
    for i in range(g.level_count()):
        lv = g.LEVELS[i]
        assert (lv.get("name_en") or "").strip(), i
        assert (lv.get("place_en") or "").strip(), i
        assert ((lv.get("building") or {}).get("name_en") or "").strip(), i


def test_check_english_content_passes():
    ok, problems = g.check_english_content()
    assert ok, problems


# --- Accessors: default is German, en switches; historical keys keep German names

def test_classes_display_default_is_german_en_switches_under_same_keys():
    de = g.classes_display()
    en = g.classes_display("en")
    a_de = next(c for c in de if c["id"] == "A")
    a_en = next(c for c in en if c["id"] == "A")
    assert a_de["name_de"] == "Brandklasse A"          # default unchanged
    assert a_en["name_de"] == "Class A"                # English under the historical key
    assert a_de.keys() == a_en.keys()                  # no key added/removed
    assert a_en["card_de"] != a_de["card_de"]          # the meet-the-fire card switched too


def test_tools_display_default_vs_en():
    w_de = next(t for t in g.tools_display() if t["id"] == "water")
    w_en = next(t for t in g.tools_display("en") if t["id"] == "water")
    assert w_de["name_de"] == "Wasser" and w_en["name_de"] == "Water"
    assert w_de["short"] == "H₂O" and w_en["short"] == "H₂O"
    m_en = next(t for t in g.tools_display("en") if t["id"] == "metal")
    assert m_en["name_de"] == "Specialist metal powder (class D)" and m_en["short"] == "Metal"


def test_feedback_reason_default_de_vs_en_verbatim():
    assert g.feedback_reason("electrical", "water").startswith("Wasser")   # default German
    assert (g.feedback_reason("electrical", "water", "en") ==
            "Water conducts electricity – risk of electric shock. Better use Carbon dioxide (CO₂).")
    assert (g.feedback_reason("F", "water", "en") ==
            "Water in a fat fire causes a fat explosion (a fireball). Better use Wet chemical (class F).")


def test_anton_accessors_default_de_vs_en():
    assert g.anton_de(("class_cards", "F")).startswith("Fett")           # default German
    assert g.anton_de(("class_cards", "F"), "en").startswith("Fat in the fryer")
    fin_en = g.finale_de("en")
    assert fin_en["lines"] and "equipment" in " ".join(fin_en["lines"]).lower()
    assert g.finale_de()["lines"] != fin_en["lines"]                     # German finale differs
    arc_en = g.anton_arc_de("en")
    assert len(arc_en) == len(g.anton_arc_de()) and arc_en != g.anton_arc_de()


def test_level_json_default_de_vs_en_and_no_internal_key_leaks():
    de = g.level_json(0)
    en = g.level_json(0, "en")
    assert de["name"] == "Die Nacht des Fachwerkfeuers"
    assert en["name"] == "The Night of the Timber-Frame Fire"
    assert de["place_de"] != en["place_de"]
    assert de["building"]["name_de"] == "Wohnhaus" and en["building"]["name_de"] == "House"
    assert "name_en" not in en["building"]           # the internal English key never leaks out
    assert de["building"].keys() == en["building"].keys()
    assert en["anton"]["hint"].startswith("Grease fires")


# --- The control exists + the i18n mechanism is wired (named tr, not t) --------

def test_langtoggle_control_and_i18n_mechanism_present():
    html = g.render_game_html()
    assert 'id="langToggle"' in html
    assert 'class="seg"' in html and 'class="seg-btn"' in html
    assert 'data-lang="de"' in html and 'data-lang="en"' in html
    assert "UI_STRINGS" in html and "function tr(" in html
    assert "function setLang(" in html
    # persistence + document.documentElement.lang wiring
    assert "fd_lang" in html
    assert "document.documentElement.lang" in html


def test_langtoggle_seg_css_present():
    html = g.render_game_html()
    assert ".seg-btn" in html and ".seg-btn.active" in html


# --- API payloads: ?lang=en returns English; default == ?lang=de (byte-identical),
#     tested through web.py's framework-free payload builders (the routes wrap these).

def test_api_classes_payload_english():
    de = {c["id"]: c for c in g.api_classes_payload()}
    en = {c["id"]: c for c in g.api_classes_payload("en")}
    assert de["A"]["name_de"] == "Brandklasse A" and en["A"]["name_de"] == "Class A"


def test_api_tools_payload_english():
    en = {t["id"]: t for t in g.api_tools_payload("en")}
    assert en["water"]["name_de"] == "Water"
    assert en["co2"]["name_de"] == "Carbon dioxide (CO₂)"


def test_api_matrix_payload_reason_english():
    en = g.api_matrix_payload("en")
    row = next(x for x in en if x["class"] == "electrical" and x["tool"] == "water")
    assert "electric shock" in row["reason"]


def test_api_level_and_levels_payload_english():
    lv = g.api_level_payload(0, "en")
    assert lv["name"] == "The Night of the Timber-Frame Fire"
    assert lv["building"]["name_de"] == "House"
    idx = g.api_levels_payload("en")
    assert any(m["name"] == "The Night of the Timber-Frame Fire" for m in idx)


def test_api_anton_payload_english():
    en = g.api_anton_payload("en")
    assert en["courage"] and en["courage"][0].strip()
    assert "equipment" in " ".join(en["finale"]["lines"]).lower()


def test_home_lang_sets_html_attribute():
    assert '<html lang="en">' in g.render_game_html("en")
    assert '<html lang="de">' in g.render_game_html()


def test_default_api_payloads_are_byte_identical_to_lang_de():
    assert g.api_classes_payload() == g.api_classes_payload("de")
    assert g.api_tools_payload() == g.api_tools_payload("de")
    assert g.api_matrix_payload() == g.api_matrix_payload("de")
    assert g.api_level_payload(0) == g.api_level_payload(0, "de")
    assert g.api_levels_payload() == g.api_levels_payload("de")
    assert g.api_anton_payload() == g.api_anton_payload("de")


def test_unknown_lang_falls_back_to_german():
    assert g.api_classes_payload("fr") == g.api_classes_payload()
    assert g.api_level_payload(0, "xx") == g.api_level_payload(0)


# --- The SAME routes exercised through a real FastAPI TestClient. Skipped when the
#     web stack isn't installed (the sandbox test runner), run wherever it is. -----

def _testclient():
    pytest.importorskip("fastapi.testclient")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    return TestClient(g.build_app())


def test_api_english_via_real_testclient():
    with _testclient() as c:
        en = {x["id"]: x for x in c.get("/api/classes?lang=en").json()}
        assert en["A"]["name_de"] == "Class A"
        row = next(x for x in c.get("/api/matrix?lang=en").json()
                   if x["class"] == "electrical" and x["tool"] == "water")
        assert "electric shock" in row["reason"]
        lv = c.get("/api/level/0?lang=en").json()
        assert lv["name"] == "The Night of the Timber-Frame Fire"


def test_default_matches_lang_de_via_real_testclient():
    with _testclient() as c:
        for path in ("/api/classes", "/api/tools", "/api/matrix",
                     "/api/level/0", "/api/levels", "/api/anton"):
            assert c.get(path).json() == c.get(path + "?lang=de").json(), path


def test_home_html_lang_via_real_testclient():
    with _testclient() as c:
        assert '<html lang="en">' in c.get("/?lang=en").text
        assert '<html lang="de">' in c.get("/").text


# --- English narration safety guard ------------------------------------------

def test_english_narration_passes_the_safety_guard():
    ok, problems = g.check_narration()
    assert ok, problems


def test_english_narration_catches_a_dangerous_mistranslation(monkeypatch):
    # A perfectly safe German hint, but a DANGEROUS English mistranslation that
    # positively points to water on the live wiring — must be caught.
    missions = {k: dict(v) for k, v in g.ANTON["missions"].items()}
    missions["bibliothek"] = dict(missions["bibliothek"])
    missions["bibliothek"]["hint"] = g.L("Zuerst den Strom abschalten, niemals Wasser.",
                                         "Just pour water on the live wiring.")
    monkeypatch.setitem(g.ANTON, "missions", missions)
    ok, problems = g.check_narration()
    assert not ok
    assert any("bibliothek" in p and "water" in p for p in problems)
    # and the umbrella English-content check fails on it too
    ok2, problems2 = g.check_english_content()
    assert not ok2


def test_english_negation_uses_word_boundaries(monkeypatch):
    # "another" must NOT be read as the negation "no"/"not": an English hint that
    # positively recommends a dangerous tool while containing the word "another"
    # is still caught (the word-boundary cue matching doesn't see a negation).
    missions = {k: dict(v) for k, v in g.ANTON["missions"].items()}
    missions["feuerwerk"] = dict(missions["feuerwerk"])
    missions["feuerwerk"]["hint"] = g.L(
        "CO₂ bändigt Sprit und Kabel; niemals Wasser.",
        "Use foam here; that is another good option.")
    monkeypatch.setitem(g.ANTON, "missions", missions)
    ok, problems = g.check_narration()
    assert not ok
    # foam is dangerous on the firework stage's electrical fire — must be flagged.
    assert any("feuerwerk" in p and "foam" in p for p in problems)
