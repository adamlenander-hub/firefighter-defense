"""Tests for the served page and health payload (web.py)

Split out of the old test_app.py (Step C)."""

import firefighter_defense as g
from helpers import *  # shared test builders/play-drivers

def test_game_page_is_german_and_has_canvas():
    # Default (no lang) is German-first, byte-for-byte on the <html lang> attribute.
    html = g.render_game_html()
    assert "<html lang=\"de\">" in html
    assert "Königstein" in html
    assert "<canvas" in html


def test_game_page_can_render_in_english():
    # The German→English switch: ?lang=en flips the served <html lang> so the browser
    # (localStorage 'fd_lang' + the JS i18n) renders English with no reload.
    html_en = g.render_game_html(lang="en")
    assert "<html lang=\"en\">" in html_en
    assert "<html lang=\"de\">" not in html_en
    # the compact DE | EN segmented toggle is present
    assert 'id="langToggle"' in html_en
    assert 'data-lang="de"' in html_en and 'data-lang="en"' in html_en


def test_sound_toggle_and_effects_are_wired():
    # ITEM-019: browser-generated sound with a German mute toggle, guarded so a
    # failure is silent. This checks the wiring exists in the page; loudness and
    # autoplay-unlock can only be judged by a real-browser listen.
    html = g.render_game_html()
    assert 'id="soundToggle"' in html          # the mute checkbox
    assert 'data-i18n="ui_sound">Ton<' in html  # labelled in German (switchable), default checked
    assert "checkbox" in html and 'id="soundToggle" checked' in html
    assert "function playSound" in html         # the single guarded entry point
    assert "function initAudio" in html         # autoplay-safe unlock on user gesture
    assert "AudioContext" in html               # Web Audio API (no audio files)
    for cue in ("'good'", "'danger'", "'useless'", "'win'", "'lose'"):
        assert cue in html                      # every defined moment has a cue
    assert "fd_sound" in html                   # guarded localStorage persistence


def test_antons_karten_card_toggle_removed_cards_always_on():
    # ITEM-043: the "Antons Karten" checkbox that could hide Anton's "meet the fire"
    # info cards has been removed — the cards are always shown on first appearance of
    # each class now. Guard that the toggle, its state variable, and its change
    # handler are all gone, and that the card-show paths no longer gate on it.
    html = g.render_game_html()
    assert 'id="cardsToggle"' not in html       # the checkbox element is gone
    assert "Antons Karten" not in html          # and its German label
    assert "cardsEnabled" not in html           # state variable + every gate removed
    assert "function maybeShowCard(" in html    # the per-class card path still exists
    assert "function showMissionIntro(" in html # as does the mission-intro card path
    # the other controls in the settings row stay intact
    assert 'id="soundToggle"' in html and 'id="contrastToggle"' in html


def test_health_payload_shape():
    g.init_db()  # ensure the default db exists so schema_version reads back
    payload = g.health_payload()
    assert payload["status"] == "ok"
    assert payload["database"].endswith(".db")


# --- ITEM-038: two-tone flat art direction (visual only) ----------------------

def test_flat_palette_and_helpers_present_in_page():
    html = g.render_game_html()
    # the approved flat palette as CSS variables, for both themes
    assert "--a:#f59e0b" in html and "--e:#2f6fed" in html          # :root light
    assert "--a:#ffc247" in html and "--panel:#161a22" in html      # body.hc dark
    # the shared two-tone helpers the later visual items reuse
    assert "function shade(" in html and "function rr(" in html
    assert "function skyGradient(" in html                          # sky gradient computed once
    # panels/canvas reskinned to the flat rounded look
    assert "border-radius: 22px" in html


def test_high_contrast_still_overrides_to_a_dark_field():
    # The high-contrast toggle (ITEM-020) must still switch to a plain dark field.
    html = g.render_game_html()
    assert "body.hc{" in html
    assert "--page:#0b0d12" in html            # dark page background variable
    assert 'id="contrastToggle"' in html       # the toggle is still present


# --- ITEM-039: distinctive animated fire characters (visual only) -------------

def test_per_type_fire_characters_present():
    html = g.render_game_html()
    assert "function drawFireCharacter(" in html
    assert "function drawEvilFace(" in html and "function drawFlameBody(" in html
    # a distinct branch for each animated type Adam named + the judgement-call ones
    for branch in ("cls==='F'", "cls==='B'", "cls==='electrical'", "cls==='D'", "cls==='C'"):
        assert branch in html, branch


def test_fire_characters_keep_greyscale_safe_signalling():
    # The class LETTER badge, emoji icon, and reaction-ring shapes must still be drawn
    # (ITEM-008) — the character art is decoration on top, never a replacement.
    html = g.render_game_html()
    fire = html[html.index("function drawFire(f){"):html.index("function drawOverlay")]
    assert "cls.letter" in fire                     # letter badge
    assert "cls.icon" in fire                       # emoji icon
    assert "#b91c1c" in fire and "setLineDash([4,4])" in fire   # danger (solid red) + useless (dashed) rings
    assert "⚠" in fire                          # ⚠️ danger glyph


# --- ITEM-044 / 035 / 036: per-mission path + background + extinguisher palette --

def test_per_mission_path_materials_present():
    html = g.render_game_html()
    for fn in ("drawPathTimber", "drawPathBooks", "drawPathGravel", "drawPathChips", "drawPathCables"):
        assert "function " + fn + "(" in html, fn
    # dispatched by the level key, and path motifs are cached (computed once, not per frame)
    assert "key==='fachwerk'" in html and "key==='schlosserei'" in html
    assert "_motifCache" in html


def test_per_mission_backgrounds_present_and_dark_in_high_contrast():
    html = g.render_game_html()
    for fn in ("bgFachwerk", "bgBibliothek", "bgKurpark", "bgFeuerwerk", "bgSchlosserei"):
        assert "function " + fn + "(" in html, fn
    # per-level gradient cached (computed once), and a plain dark field in high-contrast
    assert "_bgKey" in html and "function bgGradient(" in html
    assert "if (contrastEnabled){ ctx.fillStyle='#0b0d12'" in html


def test_palette_shows_extinguisher_graphic_and_info_popup():
    html = g.render_game_html()
    # tool cards with a canvas graphic + label + info affordance
    assert "class=\"toolbtn\"" not in html  # built in JS, not static markup
    assert "'toolbtn'" in html and "'toolcv'" in html and "'toolinfo'" in html
    assert "function openToolInfo(" in html and 'id="toolInfo"' in html
    # selecting a tool still selects it for placement (game action preserved)
    assert "selectedTool=t.id" in html
    # info text is derived from the guarded matrix (no invented facts)
    assert "matrixMap[cid" in html
    # still keyboard-selectable (1..N) via the existing slot handler
    assert "function selectToolSlot(" in html


def test_fire_resistance_is_drawn_shrinking_toward_the_kill():
    html = g.render_game_html()
    assert "FIRE_HP" in html and "GOOD_HIT_DAMAGE" in html and "WEAK_HIT_DAMAGE" in html
    assert "flameScale" in html   # the flame character shrinks with remaining hp (base-anchored, merged with ITEM-051)


def test_charge_gauge_is_drawn_on_the_tower():
    html = g.render_game_html()
    assert "towerChargeFor" in html and "maxCharge" in html


def test_extinguisher_bigger_and_gauge_vertical_on_the_right():
    # ITEM-055: the placed extinguisher is drawn 50% bigger (26x36 -> 39x54).
    # ITEM-054: the charge gauge is a vertical bar to the RIGHT of the extinguisher,
    # not a horizontal bar underneath it.
    html = g.render_game_html()
    tower = html[html.index("function drawTower(tw){"):html.index("function drawSprays")]
    assert "var w=39, h=54" in tower            # ITEM-055: 1.5x bigger extinguisher
    assert "x + w/2 + 4" in tower               # ITEM-054: gauge positioned to the right
    assert "gh=h*0.82" in tower                 # ITEM-054: gauge is tall (vertical), not a 5px-high bar


def test_build_spot_is_solid_black_with_white_border_in_all_modes():
    # ITEM-056 (replaces ITEM-049): an open build spot is a solid black circle with a
    # white border, drawn identically whether high-contrast is on or off.
    html = g.render_game_html()
    spot = html[html.index("function drawBuildSpot(x,y){"):html.index("function drawKeyHighlight")]
    assert "fillStyle='#000000'" in spot and "arc(x,y,24" in spot   # solid black disc
    assert "strokeStyle='#ffffff'" in spot                          # white border
    assert "contrastEnabled" not in spot                            # same in all modes (no per-mode branch)


def test_remove_tower_reachable_by_touch_and_keyboard_in_js():
    html = g.render_game_html()
    assert "function removeTower(spotIndex)" in html
    # touch/click path: tapping an occupied spot with no tool selected removes it,
    # kept distinct from placeTower's own logic (ITEM-042 requirement).
    assert "function boardTapAt(" in html
    assert "towerAt(i)){ keyIndex=i; removeTower(i); }" in html
    # keyboard parity (ITEM-020): Delete/Backspace removes the highlighted tower.
    assert "k==='Delete'||k==='Backspace'" in html


# --- ITEM-033: house damage stages + Anton flees (visual/narration only) ------

def test_building_damage_stage_reflects_remaining_lives_in_js():
    html = g.render_game_html()
    assert "function buildingDamageStage()" in html
    # ITEM-058 reworked the ITEM-033 damage visuals into the house-fire helpers; the
    # staged overlay is drawn by drawHouseDamage() using houseFlame() etc.
    assert "function drawHouseDamage(" in html and "function houseFlame(" in html


def test_anton_worry_and_flee_are_present_and_separate_from_bravery_in_js():
    html = g.render_game_html()
    assert "function antonWorryFactor()" in html
    assert "function antonBraveryFactor()" in html
    # worry is driven by THIS level's lives, not by campaign/win progress
    assert "game.lives / start" in html
    # Anton flees once lives hit zero, and his win-side helmet/finale arc is
    # unaffected: antonWearsHelmet() still depends only on campaignProgress.
    assert "game.lives<=0 && game.fledAt" in html
    assert "function antonWearsHelmet(){\n      var tot = campaignTotal() || 4;\n      return campaignProgress >= tot;" in html


# --- ITEM-053: responsive "landscape-phone" layout (Option B, menu) -----------
# These are light drift guards on the generated page string, not a browser test:
# they check the new landscape media query, the two menu buttons, the settings
# wrapper, and the corner-info CSS are present, and that the menu buttons default
# to hidden so desktop/portrait rendering can't regress.

def test_landscape_media_query_present():
    html = g.render_game_html()
    assert "@media (orientation: landscape) and (max-height: 500px)" in html


def test_menu_dom_additions_present():
    html = g.render_game_html()
    assert 'id="missionMenuBtn"' in html
    assert 'id="gearMenuBtn"' in html
    assert 'class="menu-btn"' in html
    assert 'id="settingsGroup"' in html


def test_menu_buttons_hidden_by_default_outside_landscape_query():
    html = g.render_game_html()
    # the default (non-media-query) rule must hide the menu buttons; only the
    # landscape media query above re-enables them, so desktop/portrait never see
    # a "Mission"/"⚙" chip that isn't there today.
    style_and_media = html.split("@media (orientation: landscape) and (max-height: 500px)")[0]
    assert ".menu-btn { display: none; }" in style_and_media or ".menu-btn{display:none}" in style_and_media.replace(" ", "")


def test_settings_group_is_a_no_op_wrapper_outside_landscape_query():
    html = g.render_game_html()
    # display:contents keeps #settingsGroup's children as direct flex items of the
    # STATUS bar outside the landscape query, so desktop layout is unchanged.
    style_and_media = html.split("@media (orientation: landscape) and (max-height: 500px)")[0]
    assert "#settingsGroup { display: contents; }" in style_and_media or \
           "#settingsGroup{display:contents}" in style_and_media.replace(" ", "")


def test_corner_info_badge_css_present():
    html = g.render_game_html()
    assert ".toolinfo::before" in html
    assert 'content: "ℹ"' in html or 'content:"ℹ"' in html.replace(" ", "")


def test_landscape_toolpalette_is_a_two_column_side_grid():
    html = g.render_game_html()
    block = _landscape_block(html)
    # #toolPalette is an absolutely-positioned block pinned to the right edge, laid
    # out as a 2-columns-of-3 grid so all six extinguishers fit a short landscape
    # screen without scrolling off the bottom — all inside the query.
    assert "#toolPalette {" in block
    tp = block.split("#toolPalette {", 1)[1].split("}", 1)[0]
    assert "position: absolute" in tp
    assert "grid-template-columns: repeat(2" in tp
    assert "right:" in tp
    assert "overflow-y: auto" in tp


def test_landscape_modals_fit_screen_with_reachable_button():
    html = g.render_game_html()
    block = _landscape_block(html)
    # instruction/story modals are capped to the viewport height and scroll inside,
    # and the primary dismiss button is pinned (sticky) so it stays reachable in
    # landscape rather than falling below the fold.
    assert "max-height: calc(100dvh - .6rem)" in block
    # only the long text scrolls, so the dismiss button stays visible at the bottom.
    assert "#cardText" in block and "#pregameText" in block
    assert "overflow-y: auto" in block


def test_intro_moves_icon_and_attribution_to_bottom_of_text():
    html = g.render_game_html()
    # the mission intro keeps the top clear (no icon) and hides the static attribution,
    # appending the ghost + name to the bottom of the scrollable info text instead.
    assert 'id="cardAttrib"' in html
    assert "document.getElementById('cardIcon').textContent = ''" in html
    assert "— Anton, der Burggeist" in html


def test_landscape_board_makes_room_for_the_strip():
    html = g.render_game_html()
    block = _landscape_block(html)
    # the board reserves room on the right for the strip and raises its height budget.
    assert "padding-right:" in block
    assert "max-height: calc(100dvh - 96px)" in block


def test_landscape_inline_hint_is_hidden():
    html = g.render_game_html()
    block = _landscape_block(html)
    assert "#hint { display: none; }" in block


def test_pregame_overlay_exists_with_dismiss_control():
    html = g.render_game_html()
    # the pre-game instruction overlay element + its dismiss button/label exist.
    assert 'id="pregame"' in html
    assert 'id="pregameText"' in html
    assert 'id="pregameOk"' in html
    assert "Los geht's" in html


def test_pregame_is_gated_by_the_matchmedia_landscape_guard():
    html = g.render_game_html()
    # showing the pre-game screen is gated by the exact landscape matchMedia query,
    # so desktop/portrait never trigger it.
    assert 'matchMedia("(orientation: landscape) and (max-height: 500px)")' in html
    assert "function maybeShowPregame(" in html
    # Esc/backdrop/button dismissal wiring is present.
    assert "function hidePregame(" in html
